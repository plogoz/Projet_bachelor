"""
Visualize a gate-level netlist DiGraph.

Public API
----------
visualize(graph, output=None, layout="dot")

Requires matplotlib and (optionally) pygraphviz for the 'dot' layout.
Falls back to spring_layout when graphviz is unavailable.
"""

from __future__ import annotations

import networkx as nx

from .graph_builder import _PORT_PREFIX


def visualize(
    graph: nx.DiGraph,
    output: str | None = None,
    layout: str = "dot",
) -> None:
    """Draw the netlist graph.

    Parameters
    ----------
    graph:
        DiGraph from build_graph().
    output:
        File path to save the image (PNG/PDF/SVG).  None → interactive window.
    layout:
        'dot' (hierarchical, requires pygraphviz), 'spring', or 'kamada_kawai'.
    """
    import matplotlib.pyplot as plt

    # Split nodes into gates and ports for distinct styling.
    gate_nodes = [n for n, d in graph.nodes(data=True) if d.get("kind") == "gate"]
    port_nodes = [n for n, d in graph.nodes(data=True) if d.get("kind") == "port"]

    # Compute layout.
    pos: dict
    if layout == "dot":
        try:
            pos = nx.nx_agraph.graphviz_layout(graph, prog="dot")
        except Exception:
            pos = nx.spring_layout(graph, seed=42)
    elif layout == "kamada_kawai":
        pos = nx.kamada_kawai_layout(graph)
    else:
        pos = nx.spring_layout(graph, seed=42)

    fig, ax = plt.subplots(figsize=(max(8, len(graph) * 0.6), 6))

    # Gate nodes — blue circles.
    nx.draw_networkx_nodes(
        graph,
        pos,
        nodelist=gate_nodes,
        node_color="steelblue",
        node_size=600,
        ax=ax,
    )
    # Port nodes — orange squares (drawn as circles with different color).
    nx.draw_networkx_nodes(
        graph,
        pos,
        nodelist=port_nodes,
        node_color="darkorange",
        node_size=400,
        node_shape="s",
        ax=ax,
    )

    # Labels: strip __port__ prefix for readability.
    labels = {
        n: n[len(_PORT_PREFIX) :] if n.startswith(_PORT_PREFIX) else n
        for n in graph.nodes()
    }
    nx.draw_networkx_labels(graph, pos, labels=labels, font_size=7, ax=ax)

    # Edges.
    nx.draw_networkx_edges(
        graph,
        pos,
        arrows=True,
        arrowsize=15,
        edge_color="gray",
        ax=ax,
    )

    # Edge labels only for small graphs (avoids clutter).
    if len(graph) <= 30:
        edge_labels = {(u, v): d.get("net", "") for u, v, d in graph.edges(data=True)}
        nx.draw_networkx_edge_labels(
            graph,
            pos,
            edge_labels=edge_labels,
            font_size=6,
            ax=ax,
        )

    ax.set_title(
        f"Netlist: {graph.graph.get('module', {}) and graph.graph['module'].name}"
    )
    ax.axis("off")
    plt.tight_layout()

    if output:
        plt.savefig(output, dpi=150, bbox_inches="tight")
        print(f"Graph saved to {output}")
    else:
        plt.show()
