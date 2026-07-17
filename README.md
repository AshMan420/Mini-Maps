# Mini-Maps

**How Google Maps finds routes — built from scratch on real Goa roads.**

Download the actual road network of Goa from OpenStreetMap, route between any two points with hand-implemented Dijkstra and A*, and *see* the difference on an interactive map: Dijkstra's explored nodes form a blob spreading blindly from the start; A*'s form a cone aimed at the destination. Same optimal route, a fraction of the work.

Pure Python, zero dependencies.

## Quick start

```bash
# 1. download Goa's roads (Overpass API, ~1 min, run once)
python -m minimaps fetch goa.osm

# 2. route: BITS Goa gate -> Panjim bus stand, with a map
python -m minimaps route goa.osm 15.391,73.878 15.4966,73.833 --viz route.html

# 3. benchmark the two algorithms over random routes
python -m minimaps bench goa.osm --pairs 30
```

`route` prints the drive time and a comparison table (nodes explored, runtime per algorithm); `--viz` writes a self-contained interactive map you can open in any browser.

## How it works, top to bottom

**Roads become a graph** (`osm.py`). OSM gives you nodes (points) and ways (roads as node lists with tags). The parser streams the XML (`iterparse`, so 100 MB extracts don't need 100 MB of RAM), keeps drivable ways, and — the key decision — weights each edge by **travel time**, not distance: segment length ÷ assumed speed for the road class (80 km/h motorway, 25 km/h residential). That's why the router prefers a longer highway over a shorter village lane, same as Google. One-way streets become directed edges, roundabouts are implicitly one-way, and only the largest connected component is kept (OSM extracts are full of disconnected fragments that would make routes silently impossible).

**Dijkstra** (`routing.py`) is the textbook algorithm with a lazy-deletion binary heap: settle the closest unsettled node, relax its edges, repeat. Correct, optimal — and blind: it expands in every direction equally, so a BITS→Panjim query happily explores Margao.

**A\*** is Dijkstra with one line changed:

```
Dijkstra:  priority = time_from_start
A*:        priority = time_from_start + straight_line_time_to_goal
```

The heuristic is the haversine distance divided by the fastest speed *in the graph* — derived from the data itself, so it never overestimates the remaining time (**admissible**), which is the exact condition under which A* is still guaranteed optimal. The search bends toward the goal, exploring a fraction of the nodes.

Both return every settled node, and `--viz` plots them (Leaflet + OpenStreetMap tiles, self-contained HTML). `bench` runs both over random pairs and asserts they always agree on the optimal cost — A* being faster is only interesting because the answer is provably identical.

**Honest caveat you should know:** A*'s advantage depends on the network. On a uniform-speed grid going corner-to-corner (its theoretical worst case — every node looks equally promising), it barely wins: 381 vs 400 nodes in our test. On real road networks with fast highways and diagonal queries, expect several-fold fewer nodes explored. Run `bench` and quote *your* measured numbers, not folklore.

## Architecture

```
fetch (Overpass) ──► osm.py ──► routing.py ──► viz.py (Leaflet HTML)
                     (graph)    (Dijkstra/A*,      ▲
                                 explored logs) ───┘
```

| Module | Responsibility |
|---|---|
| `geo.py` | haversine distance |
| `osm.py` | streaming OSM parser, travel-time graph, largest component |
| `routing.py` | Dijkstra + A*, instrumented with explored-node logs |
| `viz.py` | self-contained interactive map (route + explored sets) |
| `cli.py` | fetch / route / bench |

## Tests

```bash
pip install pytest
pytest tests/ -v
```

11 tests: the OSM parser on a hand-built map fixture (one-ways, footpath exclusion, component pruning, time-vs-distance weights, nearest-node snapping) and routing on a synthetic city grid (optimality equality between algorithms, heuristic admissibility spot-checks, valid path reconstruction, unreachable handling).

## Future work

- **Contraction Hierarchies** — the preprocessing technique behind Maps' millisecond answers; the natural big next step
- Bidirectional Dijkstra (meet in the middle) — easier than CH, ~2x fewer nodes
- k-d tree for nearest-node snapping (currently a linear scan)
- Turn restrictions and traffic-signal penalties from OSM tags
- Public transport routing (GTFS import) for cities that publish feeds
