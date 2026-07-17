"""Dijkstra and A*, instrumented so you can SEE the difference.

Both return not just the route but every node they settled along the way.
Plotted on a map, Dijkstra's explored set is a circular blob around the
start (it expands blindly in all directions), while A*'s is a narrow cone
aimed at the destination. Same optimal route, wildly different work — that
picture is the whole point of this project.

A*'s only change to Dijkstra is the priority:

    Dijkstra:  priority = time_from_start
    A*:        priority = time_from_start + straight_line_time_to_goal

The heuristic (straight-line distance at the fastest road speed) never
overestimates the real remaining time — it's "admissible" — which is the
condition that guarantees A* still finds the true optimum.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from time import perf_counter

from .geo import haversine_m
from .osm import Graph, MAX_SPEED_MS


@dataclass
class RouteResult:
    found: bool
    seconds: float                    # travel time of the route
    path: list[int]                   # node ids, start -> goal
    explored: list[int]               # settled nodes, in settle order
    runtime_ms: float
    algorithm: str

    @property
    def explored_count(self) -> int:
        return len(self.explored)


def _reconstruct(prev: dict[int, int], goal: int) -> list[int]:
    path = [goal]
    while path[-1] in prev:
        path.append(prev[path[-1]])
    return path[::-1]


def _search(graph: Graph, src: int, dst: int, heuristic) -> tuple[dict, list, float | None]:
    dist = {src: 0.0}
    prev: dict[int, int] = {}
    settled: set[int] = set()
    explored: list[int] = []
    pq: list[tuple[float, int]] = [(heuristic(src), src)]

    while pq:
        _, node = heapq.heappop(pq)
        if node in settled:
            continue  # stale queue entry (lazy deletion)
        settled.add(node)
        explored.append(node)
        if node == dst:
            return prev, explored, dist[node]
        for nbr, w in graph.adj[node]:
            nd = dist[node] + w
            if nd < dist.get(nbr, float("inf")):
                dist[nbr] = nd
                prev[nbr] = node
                heapq.heappush(pq, (nd + heuristic(nbr), nbr))
    return prev, explored, None


def dijkstra(graph: Graph, src: int, dst: int) -> RouteResult:
    t0 = perf_counter()
    prev, explored, cost = _search(graph, src, dst, lambda n: 0.0)
    ms = (perf_counter() - t0) * 1000
    if cost is None:
        return RouteResult(False, 0.0, [], explored, ms, "dijkstra")
    return RouteResult(True, cost, _reconstruct(prev, dst), explored, ms, "dijkstra")


def astar(graph: Graph, src: int, dst: int) -> RouteResult:
    dlat, dlon = graph.coords[dst]
    speed = graph.max_speed_ms()  # data-derived: admissible by construction

    def h(n: int) -> float:
        lat, lon = graph.coords[n]
        return haversine_m(lat, lon, dlat, dlon) / speed

    t0 = perf_counter()
    prev, explored, cost = _search(graph, src, dst, h)
    ms = (perf_counter() - t0) * 1000
    if cost is None:
        return RouteResult(False, 0.0, [], explored, ms, "astar")
    return RouteResult(True, cost, _reconstruct(prev, dst), explored, ms, "astar")


ALGORITHMS = {"dijkstra": dijkstra, "astar": astar}
