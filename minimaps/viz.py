"""Write a self-contained HTML map (Leaflet via CDN) showing the route and,
crucially, every node the algorithm explored. Open it in any browser.

Side-by-side mode draws Dijkstra's explored set and A*'s on the same map —
the blob vs the cone. That single image explains the speedup better than
any table.
"""

from __future__ import annotations

import json
from pathlib import Path

from .osm import Graph
from .routing import RouteResult

_PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Mini-Maps</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  html, body, #map { height: 100%; margin: 0; }
  .legend { background: #fff; padding: 8px 12px; border-radius: 6px;
            font: 13px/1.6 system-ui, sans-serif; box-shadow: 0 1px 4px rgba(0,0,0,.3); }
  .dot { display: inline-block; width: 10px; height: 10px; border-radius: 5px;
         margin-right: 6px; }
</style></head><body>
<div id="map"></div>
<script>
const DATA = __DATA__;
const map = L.map('map');
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
  {attribution: '&copy; OpenStreetMap contributors'}).addTo(map);

const legend = L.control({position: 'topright'});
legend.onAdd = () => {
  const div = L.DomUtil.create('div', 'legend');
  div.innerHTML = DATA.layers.map(l =>
    `<div><span class="dot" style="background:${l.color}"></span>` +
    `${l.name}: ${l.explored.length.toLocaleString()} nodes explored, ` +
    `${l.runtime_ms.toFixed(1)} ms</div>`).join('') +
    (DATA.route_minutes !== null ?
      `<div style="margin-top:4px"><b>route: ${DATA.route_minutes.toFixed(1)} min drive</b></div>` : '');
  return div;
};
legend.addTo(map);

for (const layer of DATA.layers) {
  // explored nodes as a low-cost canvas layer
  const canvas = L.canvas({padding: 0.2});
  for (const [lat, lon] of layer.explored) {
    L.circleMarker([lat, lon], {renderer: canvas, radius: 1.5,
      color: layer.color, opacity: 0.45, fill: true}).addTo(map);
  }
}
// the route on top, in bold
if (DATA.route.length) {
  const line = L.polyline(DATA.route, {color: '#d62728', weight: 5}).addTo(map);
  map.fitBounds(line.getBounds().pad(0.25));
  L.marker(DATA.route[0]).addTo(map).bindPopup('start');
  L.marker(DATA.route[DATA.route.length - 1]).addTo(map).bindPopup('goal');
} else if (DATA.layers.length && DATA.layers[0].explored.length) {
  map.fitBounds(L.latLngBounds(DATA.layers[0].explored).pad(0.25));
} else {
  map.setView([15.45, 73.85], 11); // Goa
}
</script></body></html>"""

_COLORS = {"dijkstra": "#1f77b4", "astar": "#2ca02c"}
MAX_DRAWN = 15_000  # cap per layer so huge searches don't melt the browser


def _sample(nodes: list, cap: int) -> list:
    if len(nodes) <= cap:
        return nodes
    step = len(nodes) / cap
    return [nodes[int(i * step)] for i in range(cap)]


def write_map(
    graph: Graph,
    results: list[RouteResult],
    out_path: str | Path,
) -> Path:
    """Render one or more search results (same src/dst) to an HTML file."""
    route_result = next((r for r in results if r.found), None)
    data = {
        "route": [
            [graph.coords[n][0], graph.coords[n][1]]
            for n in (route_result.path if route_result else [])
        ],
        "route_minutes": route_result.seconds / 60 if route_result else None,
        "layers": [
            {
                "name": r.algorithm,
                "color": _COLORS.get(r.algorithm, "#777"),
                "runtime_ms": r.runtime_ms,
                "explored": [
                    [round(graph.coords[n][0], 5), round(graph.coords[n][1], 5)]
                    for n in _sample(r.explored, MAX_DRAWN)
                ],
            }
            for r in results
        ],
    }
    out = Path(out_path)
    out.write_text(_PAGE.replace("__DATA__", json.dumps(data)), encoding="utf-8")
    return out
