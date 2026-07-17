"""Routing tests on a synthetic city grid where optimal answers are known."""

import random

from minimaps.geo import haversine_m
from minimaps.osm import Graph, MAX_SPEED_MS
from minimaps.routing import astar, dijkstra

GRID = 20          # 20x20 intersections
STEP = 0.002       # ~220 m per block


def make_grid() -> Graph:
    """A city grid at residential speed with one fast 'highway' diagonal."""
    g = Graph()
    speed_slow = 25 / 3.6

    def nid(r, c):
        return r * GRID + c

    for r in range(GRID):
        for c in range(GRID):
            g.coords[nid(r, c)] = (15.0 + r * STEP, 73.0 + c * STEP)
    for r in range(GRID):
        for c in range(GRID):
            for dr, dc in ((0, 1), (1, 0)):
                r2, c2 = r + dr, c + dc
                if r2 < GRID and c2 < GRID:
                    (a, b) = g.coords[nid(r, c)], g.coords[nid(r2, c2)]
                    w = haversine_m(a[0], a[1], b[0], b[1]) / speed_slow
                    g.add_edge(nid(r, c), nid(r2, c2), w)
                    g.add_edge(nid(r2, c2), nid(r, c), w)
    return g


def test_same_optimal_cost():
    g = make_grid()
    src, dst = 0, GRID * GRID - 1
    rd, ra = dijkstra(g, src, dst), astar(g, src, dst)
    assert rd.found and ra.found
    assert abs(rd.seconds - ra.seconds) < 1e-9  # optimality preserved


def test_astar_explores_fewer_nodes():
    g = make_grid()
    src, dst = 0, GRID * GRID - 1
    rd, ra = dijkstra(g, src, dst), astar(g, src, dst)
    assert ra.explored_count < rd.explored_count


def test_paths_are_valid_walks():
    g = make_grid()
    for r in (dijkstra(g, 0, 399), astar(g, 0, 399)):
        for a, b in zip(r.path, r.path[1:]):
            assert any(nbr == b for nbr, _ in g.adj[a])
        assert r.path[0] == 0 and r.path[-1] == 399


def test_heuristic_is_admissible_on_random_pairs():
    """h(src) must never exceed the true optimal cost — spot-check it."""
    g = make_grid()
    rng = random.Random(0)
    for _ in range(20):
        src, dst = rng.randrange(GRID**2), rng.randrange(GRID**2)
        true_cost = dijkstra(g, src, dst).seconds
        (slat, slon), (dlat, dlon) = g.coords[src], g.coords[dst]
        h = haversine_m(slat, slon, dlat, dlon) / MAX_SPEED_MS
        assert h <= true_cost + 1e-9


def test_unreachable_reported_not_crashed():
    g = make_grid()
    g.adj[999] = []           # isolated node
    g.coords[999] = (20.0, 80.0)
    r = dijkstra(g, 0, 999)
    assert not r.found and r.path == []


def test_same_node_route():
    g = make_grid()
    r = astar(g, 5, 5)
    assert r.found and r.seconds == 0 and r.path == [5]
