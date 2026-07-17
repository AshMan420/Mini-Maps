"""Parse OpenStreetMap XML into a routable road graph.

OSM's data model is beautifully simple:
  * <node>  — a point on Earth (id, lat, lon)
  * <way>   — an ordered list of node refs + key/value tags; a road is a
              way whose 'highway' tag is a road type we can drive on

Turning that into a graph means: keep drivable ways, connect consecutive
nodes with edges weighted by TRAVEL TIME (length / speed for the road
class — this is why the router prefers a longer highway over a shorter
village lane, same as Google), respect one-way streets, and finally keep
only the largest connected component so every remaining pair of nodes is
actually reachable (OSM extracts are full of disconnected fragments —
private roads, ferry docks, mapping errors).

Parsing uses ElementTree.iterparse so a 100 MB extract streams through
without loading the whole XML tree into memory.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from .geo import haversine_m

# road class -> assumed speed (km/h). The tag values are OSM's, the speeds
# are sane Indian-road defaults; tweak freely.
SPEEDS_KMH = {
    "motorway": 80, "trunk": 70, "primary": 60, "secondary": 50,
    "tertiary": 40, "unclassified": 30, "residential": 25,
    "motorway_link": 45, "trunk_link": 40, "primary_link": 35,
    "secondary_link": 30, "tertiary_link": 25,
    "living_street": 15, "service": 15,
}

MAX_SPEED_MS = max(SPEEDS_KMH.values()) / 3.6  # used by the A* heuristic


@dataclass
class Graph:
    coords: dict[int, tuple[float, float]] = field(default_factory=dict)
    adj: dict[int, list[tuple[int, float]]] = field(default_factory=dict)  # node -> [(nbr, seconds)]

    @property
    def num_nodes(self) -> int:
        return len(self.adj)

    @property
    def num_edges(self) -> int:
        return sum(len(v) for v in self.adj.values())

    def max_speed_ms(self) -> float:
        """Fastest speed actually present in this graph (m/s), derived from
        the data itself: max over edges of distance/time. Using this for the
        A* heuristic keeps it admissible *by construction* — even if the map
        has no highways, the heuristic tightens to match, instead of being
        uselessly conservative."""
        if not hasattr(self, "_max_speed_ms"):
            best = 1.0
            for a, nbrs in self.adj.items():
                la, lo = self.coords[a]
                for b, w in nbrs:
                    if w > 0:
                        lb, lob = self.coords[b]
                        best = max(best, haversine_m(la, lo, lb, lob) / w)
            self._max_speed_ms = best
        return self._max_speed_ms

    def add_edge(self, a: int, b: int, seconds: float) -> None:
        self.adj.setdefault(a, []).append((b, seconds))
        self.adj.setdefault(b, [])  # ensure b exists even if one-way dead end

    def nearest_node(self, lat: float, lon: float) -> int:
        """Snap a lat/lon to the closest graph node (linear scan — fine for
        a state-sized extract; a k-d tree is the obvious upgrade)."""
        return min(
            self.adj,
            key=lambda n: (self.coords[n][0] - lat) ** 2
            + (self.coords[n][1] - lon) ** 2,
        )


def parse_osm(path: str | Path) -> Graph:
    """Stream-parse OSM XML into a Graph (largest connected component)."""
    coords: dict[int, tuple[float, float]] = {}
    graph = Graph()

    way_nodes: list[int] = []
    tags: dict[str, str] = {}
    in_way = False

    for event, elem in ET.iterparse(str(path), events=("start", "end")):
        if event == "start":
            if elem.tag == "way":
                in_way, way_nodes, tags = True, [], {}
            continue
        # end events
        if elem.tag == "node":
            coords[int(elem.get("id"))] = (float(elem.get("lat")), float(elem.get("lon")))
        elif elem.tag == "nd" and in_way:
            way_nodes.append(int(elem.get("ref")))
        elif elem.tag == "tag" and in_way:
            tags[elem.get("k")] = elem.get("v")
        elif elem.tag == "way":
            _add_way(graph, coords, way_nodes, tags)
            in_way = False
        elem.clear()  # free memory as we go

    graph.coords = {n: coords[n] for n in graph.adj}
    return _largest_component(graph)


def _add_way(graph: Graph, coords, way_nodes: list[int], tags: dict) -> None:
    speed = SPEEDS_KMH.get(tags.get("highway", ""))
    if speed is None:
        return  # not a drivable road (footpath, building, river...)
    if tags.get("access") in ("no", "private"):
        return
    oneway = tags.get("oneway", "no")
    if tags.get("junction") == "roundabout":
        oneway = "yes"  # roundabouts are implicitly one-way in OSM
    nodes = way_nodes if oneway != "-1" else list(reversed(way_nodes))

    speed_ms = speed / 3.6
    for a, b in zip(nodes, nodes[1:]):
        if a not in coords or b not in coords:
            continue  # way references a node outside the extract's bbox
        (la, lo), (lb, lob) = coords[a], coords[b]
        seconds = haversine_m(la, lo, lb, lob) / speed_ms
        graph.add_edge(a, b, seconds)
        if oneway not in ("yes", "true", "1", "-1"):
            graph.add_edge(b, a, seconds)


def _largest_component(graph: Graph) -> Graph:
    """Keep only the biggest weakly-connected component."""
    undirected: dict[int, set[int]] = {n: set() for n in graph.adj}
    for a, nbrs in graph.adj.items():
        for b, _ in nbrs:
            undirected[a].add(b)
            undirected[b].add(a)

    seen: set[int] = set()
    best: set[int] = set()
    for start in graph.adj:
        if start in seen:
            continue
        comp = {start}
        queue = deque([start])
        while queue:
            n = queue.popleft()
            for m in undirected[n]:
                if m not in comp:
                    comp.add(m)
                    queue.append(m)
        seen |= comp
        if len(comp) > len(best):
            best = comp

    out = Graph()
    out.coords = {n: graph.coords[n] for n in best}
    out.adj = {
        n: [(b, w) for b, w in graph.adj[n] if b in best] for n in best
    }
    return out
