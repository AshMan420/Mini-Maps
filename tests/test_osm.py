"""Parser tests on a hand-built OSM fixture where we know every edge."""

import textwrap

import pytest

from minimaps.osm import parse_osm

# A tiny map: a 3-node primary road, a residential side road, a one-way
# street, a footpath (must be ignored), and a disconnected private lane.
FIXTURE = textwrap.dedent("""\
    <?xml version="1.0"?>
    <osm version="0.6">
      <node id="1" lat="15.4000" lon="73.8000"/>
      <node id="2" lat="15.4010" lon="73.8000"/>
      <node id="3" lat="15.4020" lon="73.8000"/>
      <node id="4" lat="15.4010" lon="73.8010"/>
      <node id="5" lat="15.4020" lon="73.8010"/>
      <node id="6" lat="15.5000" lon="73.9000"/>
      <node id="7" lat="15.5010" lon="73.9000"/>
      <way id="100">
        <nd ref="1"/><nd ref="2"/><nd ref="3"/>
        <tag k="highway" v="primary"/>
      </way>
      <way id="101">
        <nd ref="2"/><nd ref="4"/>
        <tag k="highway" v="residential"/>
      </way>
      <way id="102">
        <nd ref="4"/><nd ref="5"/>
        <tag k="highway" v="residential"/>
        <tag k="oneway" v="yes"/>
      </way>
      <way id="103">
        <nd ref="3"/><nd ref="5"/>
        <tag k="highway" v="footway"/>
      </way>
      <way id="104">
        <nd ref="6"/><nd ref="7"/>
        <tag k="highway" v="residential"/>
      </way>
    </osm>
""")


@pytest.fixture
def graph(tmp_path):
    f = tmp_path / "map.osm"
    f.write_text(FIXTURE)
    return parse_osm(f)


def test_footway_excluded_and_component_pruned(graph):
    # nodes 6,7 are a separate fragment -> dropped; footway never linked 3-5
    assert set(graph.adj) == {1, 2, 3, 4, 5}


def test_two_way_edges_are_bidirectional(graph):
    assert any(b == 2 for b, _ in graph.adj[1])
    assert any(b == 1 for b, _ in graph.adj[2])


def test_oneway_is_directed(graph):
    assert any(b == 5 for b, _ in graph.adj[4])
    assert not any(b == 4 for b, _ in graph.adj[5])


def test_weights_are_travel_time_not_distance(graph):
    # segment 1-2 (primary, 60 km/h) vs 2-4 (residential, 25 km/h):
    # similar length (~111 m vs ~107 m) but residential must cost far more time
    w_primary = next(w for b, w in graph.adj[1] if b == 2)
    w_resid = next(w for b, w in graph.adj[2] if b == 4)
    assert w_resid > w_primary * 1.8


def test_nearest_node_snapping(graph):
    assert graph.nearest_node(15.4001, 73.8001) == 1
    assert graph.nearest_node(15.4021, 73.8009) == 5
