"""
Black-box insertion into a gate-level netlist.

Public API
----------
insert_every_n(module, graph, N, bb_cell, in_port, out_port)  ->  Module

Algorithm
---------
1. Topological sort of the DiGraph → causal gate order.
2. Walk gate nodes (skip port pseudo-nodes), maintain a counter.
3. Every N-th gate, collect its output nets from the graph edges.
4. For each output net, split the wire:
       original_net  →  bb instance input
       new wire      ←  bb instance output
       downstream consumers updated to read new wire
5. Return a deep-copied Module with insertions applied.

The input Module and graph are not mutated.
"""

from __future__ import annotations

import copy

import networkx as nx

from .graph_builder import _is_output_pin, _port_node
from .netlist_parser import Instance, Module, NetRef, WireDecl


def insert_every_n(
    module: Module,
    graph: nx.DiGraph,
    N: int,
    bb_cell: str = "BLACKBOX",
    in_port: str = "IN",
    out_port: str = "OUT",
) -> Module:
    """Insert a black-box instance on the output of every N-th gate.

    Parameters
    ----------
    module:
        Original parsed netlist.  Not mutated.
    graph:
        DiGraph produced by build_graph(module).
    N:
        Insert after every N gate nodes in topological order (1-indexed).
    bb_cell, in_port, out_port:
        Cell type and port names of the black-box placeholder.

    Returns
    -------
    Module
        Deep copy of the input module with black-box instances and wires added.
    """
    if N < 1:
        raise ValueError(f"N must be >= 1, got {N}")

    mod = copy.deepcopy(module)

    # Instance lookup for easy mutation
    inst_by_name: dict[str, Instance] = {inst.name: inst for inst in mod.instances}

    bb_index = 0
    gate_count = 0

    for node in nx.topological_sort(graph):
        attrs = graph.nodes[node]
        if attrs.get("kind") != "gate":
            continue
        gate_count += 1
        if gate_count % N != 0:
            continue

        # Find output net(s) leaving this gate node in the graph.
        # graph edges are (driver, consumer, {net: wire_name}).
        output_nets: list[str] = []
        for _, _, edge_data in graph.out_edges(node, data=True):
            net = edge_data.get("net", "")
            if net and net not in output_nets:
                output_nets.append(net)

        if not output_nets:
            continue  # floating output — skip

        # Insert one black box per output net.
        for original_net in output_nets:
            new_wire = f"_bb_{bb_index}_"
            bb_index += 1

            # Add the new wire declaration.
            mod.wires[new_wire] = WireDecl(new_wire)

            # Create the black-box instance.
            bb_inst = Instance(
                cell_type=bb_cell,
                name=f"bb_{bb_index - 1}",
                connections={
                    in_port: NetRef(original_net),
                    out_port: NetRef(new_wire),
                },
            )
            mod.instances.append(bb_inst)

            # Redirect downstream consumers (instances only, not ports).
            # We need to find which instances use original_net as an input.
            # Use the graph to find consumer nodes, then patch their connections.
            for consumer_node in graph.successors(node):
                edge_data = graph.edges[node, consumer_node]
                if edge_data.get("net") != original_net:
                    continue
                consumer_attrs = graph.nodes[consumer_node]
                if consumer_attrs.get("kind") != "gate":
                    continue
                consumer_inst = inst_by_name.get(consumer_node)
                if consumer_inst is None:
                    continue
                # Update any connection referencing original_net.
                for pin, ref in list(consumer_inst.connections.items()):
                    if str(ref) == original_net or ref.name == original_net:
                        consumer_inst.connections[pin] = NetRef(
                            new_wire, ref.msb, ref.lsb
                        )

    return mod
