"""
Netlist editing tool — CLI entry point.

Usage
-----
python -m netlist_tool INPUT.v OUTPUT.v --N 5
                                        [--bb-cell BLACKBOX]
                                        [--in-port IN --out-port OUT]
                                        [--lib path/to/cells.lib]
                                        [--visualize [FILE]]

Orchestration
-------------
1. Parse Verilog netlist  →  Module
2. (optional) Load Liberty lib  →  LibParser
3. Build NetworkX DiGraph  →  Graph
4. Insert black boxes every N gates  →  modified Module
5. Write modified netlist to OUTPUT.v
6. (optional) Visualize graph
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="netlist_tool",
        description="Insert black-box cells into a gate-level Verilog netlist.",
    )
    p.add_argument("input", type=Path, help="Input Verilog netlist (.v)")
    p.add_argument("output", type=Path, help="Output Verilog netlist (.v)")
    p.add_argument("--N", type=int, required=True, metavar="N",
                   help="Insert a black-box after every N gate instances")
    p.add_argument("--bb-cell", default="BLACKBOX", metavar="CELL",
                   help="Cell type name for the black box (default: BLACKBOX)")
    p.add_argument("--in-port", default="IN", metavar="PORT",
                   help="Input port name of the black box (default: IN)")
    p.add_argument("--out-port", default="OUT", metavar="PORT",
                   help="Output port name of the black box (default: OUT)")
    p.add_argument("--lib", type=Path, default=None, metavar="LIB",
                   help="Liberty (.lib) file for accurate pin-direction lookup")
    p.add_argument("--visualize", nargs="?", const=True, metavar="FILE",
                   help="Visualize the graph.  Optionally supply a file path to save.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    from .graph_builder import build_graph
    from .inserter import insert_every_n
    from .netlist_parser import parse
    from .serializer import write

    if not args.input.exists():
        print(f"error: input file not found: {args.input}", file=sys.stderr)
        return 1

    print(f"Parsing {args.input} ...")
    module = parse(args.input)
    print(module.summary())

    lib = None
    if args.lib is not None:
        from .lib_parser import LibParser
        lib = LibParser(args.lib)

    print(f"\nBuilding graph ...")
    graph = build_graph(module, lib)
    print(f"  {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")

    print(f"\nInserting black boxes every N={args.N} gates ...")
    modified = insert_every_n(
        module, graph, args.N,
        bb_cell=args.bb_cell,
        in_port=args.in_port,
        out_port=args.out_port,
    )
    inserted = len(modified.instances) - len(module.instances)
    print(f"  Inserted {inserted} black-box instance(s)")

    print(f"\nWriting {args.output} ...")
    write(modified, args.output)
    print("  Done.")

    if args.visualize is not None:
        from .grapher import visualize
        out_file = None if args.visualize is True else args.visualize
        visualize(graph, output=out_file)

    return 0


if __name__ == "__main__":
    sys.exit(main())
