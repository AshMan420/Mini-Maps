"""Mini-Maps CLI.

    python -m minimaps fetch goa.osm                    # download Goa roads (OSM)
    python -m minimaps route goa.osm 15.391,73.878 15.4966,73.833 --viz route.html
    python -m minimaps bench goa.osm --pairs 30

Coordinates are lat,lon. 15.391,73.878 is the BITS Goa gate.
"""

from __future__ import annotations

import argparse
import random
import sys
import urllib.request
from pathlib import Path

from .osm import parse_osm
from .routing import astar, dijkstra
from .viz import write_map

OVERPASS = "https://overpass-api.de/api/interpreter"
# Vasco–Panjim–Mapusa–Margao rectangle: covers the sample bus network too.
DEFAULT_BBOX = (15.25, 73.74, 15.62, 74.02)  # south, west, north, east


def _parse_point(s: str) -> tuple[float, float]:
    try:
        lat, lon = (float(x) for x in s.split(","))
        return lat, lon
    except ValueError:
        sys.exit(f"bad coordinate {s!r} — expected lat,lon like 15.391,73.878")


def cmd_fetch(args) -> None:
    s, w, n, e = (args.bbox and tuple(float(x) for x in args.bbox.split(","))) or DEFAULT_BBOX
    query = f'[out:xml][timeout:180];(way["highway"]({s},{w},{n},{e});>;);out;'
    print(f"downloading roads for bbox ({s},{w},{n},{e}) from Overpass...")
    print("(this is a few tens of MB and can take a minute or two)")
    req = urllib.request.Request(
        OVERPASS, data=query.encode(), headers={"User-Agent": "mini-maps student project"}
    )
    with urllib.request.urlopen(req, timeout=300) as resp, open(args.out, "wb") as fh:
        while chunk := resp.read(1 << 20):
            fh.write(chunk)
    size = Path(args.out).stat().st_size / (1 << 20)
    print(f"saved {args.out} ({size:.1f} MiB) — now try: python -m minimaps route {args.out} ...")


def _load_graph(path: str):
    if not Path(path).exists():
        sys.exit(f"{path} not found — run `python -m minimaps fetch {path}` first")
    print(f"parsing {path} ...", file=sys.stderr)
    graph = parse_osm(path)
    print(f"graph: {graph.num_nodes:,} nodes, {graph.num_edges:,} edges", file=sys.stderr)
    return graph


def cmd_route(args) -> None:
    graph = _load_graph(args.osm)
    src = graph.nearest_node(*_parse_point(args.origin))
    dst = graph.nearest_node(*_parse_point(args.dest))

    results = [dijkstra(graph, src, dst), astar(graph, src, dst)]
    d, a = results
    if not d.found:
        sys.exit("no route found (are both points inside the map area?)")

    print(f"\nroute: {d.seconds / 60:.1f} min drive, {len(d.path)} nodes")
    print(f"{'algorithm':>10}  {'explored':>10}  {'time':>9}")
    for r in results:
        print(f"{r.algorithm:>10}  {r.explored_count:>10,}  {r.runtime_ms:>7.1f}ms")
    print(f"\nA* explored {d.explored_count / max(a.explored_count, 1):.1f}x fewer nodes "
          f"for the same optimal route ({abs(d.seconds - a.seconds):.2f}s difference in cost).")

    if args.viz:
        out = write_map(graph, results, args.viz)
        print(f"map written to {out} — open it in a browser")


def cmd_bench(args) -> None:
    graph = _load_graph(args.osm)
    rng = random.Random(args.seed)
    nodes = list(graph.adj)
    pairs = [(rng.choice(nodes), rng.choice(nodes)) for _ in range(args.pairs)]

    totals = {"dijkstra": [0, 0.0], "astar": [0, 0.0]}  # explored, ms
    routes_found = 0
    for src, dst in pairs:
        rd, ra = dijkstra(graph, src, dst), astar(graph, src, dst)
        if not rd.found:
            continue
        routes_found += 1
        assert abs(rd.seconds - ra.seconds) < 1e-6, "A* returned a different cost!"
        for r in (rd, ra):
            totals[r.algorithm][0] += r.explored_count
            totals[r.algorithm][1] += r.runtime_ms

    print(f"\n{routes_found} random routes on {graph.num_nodes:,} nodes "
          f"(seed {args.seed}) — averages per query:\n")
    print(f"{'algorithm':>10}  {'explored':>10}  {'time':>9}")
    for name, (explored, ms) in totals.items():
        print(f"{name:>10}  {explored / routes_found:>10,.0f}  {ms / routes_found:>7.1f}ms")
    dj, an = totals["dijkstra"], totals["astar"]
    print(f"\nA* explores {dj[0] / max(an[0], 1):.1f}x fewer nodes, "
          f"runs {dj[1] / max(an[1], 1):.1f}x faster, always same optimal cost.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="minimaps", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("fetch", help="download OSM road data (Overpass API)")
    p.add_argument("out", nargs="?", default="goa.osm")
    p.add_argument("--bbox", help="south,west,north,east (default: central Goa)")

    p = sub.add_parser("route", help="route between two points, compare algorithms")
    p.add_argument("osm")
    p.add_argument("origin")
    p.add_argument("dest")
    p.add_argument("--viz", metavar="OUT.html", help="write an interactive map")

    p = sub.add_parser("bench", help="Dijkstra vs A* over random routes")
    p.add_argument("osm")
    p.add_argument("--pairs", type=int, default=30)
    p.add_argument("--seed", type=int, default=42)

    args = parser.parse_args(argv)
    {"fetch": cmd_fetch, "route": cmd_route, "bench": cmd_bench}[args.command](args)


if __name__ == "__main__":
    main()
