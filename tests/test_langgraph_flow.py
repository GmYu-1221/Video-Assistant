from content_creator.workflow import build_graph

def test_graph_has_expected_nodes():
    graph = build_graph()
    assert set(graph.nodes) >= {"vision_agent", "director_agent", "remotion_agent", "render_agent"}
