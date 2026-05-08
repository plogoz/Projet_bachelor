"""
Module dataclass → Verilog netlist string.

Public API
----------
serialize(module)          ->  str
write(module, path)        ->  None
"""

from __future__ import annotations

from pathlib import Path

from .netlist_parser import Module, NetRef, PortDecl, WireDecl


def _range_str(msb: int | None, lsb: int | None) -> str:
    if msb is None:
        return ""
    return f"[{msb}:{lsb}] "


def _netref_str(ref: NetRef) -> str:
    return str(ref)


def serialize(module: Module) -> str:
    lines: list[str] = []

    # Module-level Verilog attributes (e.g. (* top = 1 *)) — emitted verbatim
    # so downstream closed-source tools see the same metadata as the original.
    for attr in module.attributes:
        lines.append(f"(*{attr}*)")

    # Module header
    port_list = ", ".join(module.port_order)
    lines.append(f"module {module.name}({port_list});")

    # Port declarations, each followed by its matching wire declaration.
    # Yosys emits both, and downstream SPICE tooling depends on this layout.
    port_names = set(module.ports)
    for port_name in module.port_order:
        if port_name not in module.ports:
            continue
        p = module.ports[port_name]
        rng = _range_str(p.msb, p.lsb)
        lines.append(f"  {p.direction} {rng}{p.name};")
        lines.append(f"  wire {rng}{p.name};")

    # Internal wire declarations (ports were already paired with wires above).
    for wire_name, w in module.wires.items():
        if wire_name in port_names:
            continue
        rng = _range_str(w.msb, w.lsb)
        lines.append(f"  wire {rng}{w.name};")

    # Instances
    for inst in module.instances:
        conn_parts = ", ".join(
            f".{pin}({_netref_str(ref)})" for pin, ref in inst.connections.items()
        )
        lines.append(f"  {inst.cell_type} {inst.name} ({conn_parts});")

    # Assigns
    for a in module.assigns:
        lines.append(f"  assign {_netref_str(a.lhs)} = {_netref_str(a.rhs)};")

    lines.append("endmodule")
    return "\n".join(lines) + "\n"


def write(module: Module, path: str | Path) -> None:
    Path(path).write_text(serialize(module))
