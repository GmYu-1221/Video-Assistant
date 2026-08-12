from langgraph.graph import END, START, StateGraph
from .state import VideoState
from content_creator.agents import director_node, remotion_node, render_node, vision_node

def build_graph():
    graph = StateGraph(VideoState)
    graph.add_node("vision_agent", vision_node)
    graph.add_node("director_agent", director_node)
    graph.add_node("remotion_agent", remotion_node)
    graph.add_node("render_agent", render_node)
    graph.add_edge(START, "vision_agent")
    graph.add_edge("vision_agent", "director_agent")
    graph.add_edge("director_agent", "remotion_agent")
    graph.add_edge("remotion_agent", "render_agent")
    graph.add_edge("render_agent", END)
    return graph.compile()
