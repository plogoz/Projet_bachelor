"""
----------
Vibe coded
Verilog gate-level netlist parser
28.04.2026 @ 16h00
----------

Structural Verilog netlist parser.

Parses post-synthesis Verilog netlists (Yosys, Genus, DC, Oasys, …) into
typed dataclasses for downstream graph construction.

Public API
----------
parse(netlist_path)  ->  Module
    Read a netlist file and return a fully-typed Module.

Module
    name, port_order, ports, wires, instances, assigns.

See ``docs/verilog_netlist_grammar.md`` for the BNF and scope.

Design
------
Single pyparsing grammar; each rule has a parse action that emits the
matching dataclass. The module-level parse action filters tokens by type
to assemble the final Module. Comments and ``(* … *)`` attributes are
discarded via ``grammar.ignore(...)``.

``assign`` aliases (Yosys-only) are recorded verbatim in
``Module.assigns``; alias resolution happens in graph_builder so the
parser stays a faithful 1:1 view of the file.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pyparsing as pp

ppc = pp.common
pp.ParserElement.enable_packrat()


# ---------------------------------------------------------------------------
# 1. Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class NetRef:
    """Reference to a net or a slice of one.

    Both msb and lsb None  → whole net (scalar or whole bus).
    msb == lsb             → single-bit select.
    msb >  lsb             → range select.
    """

    name: str
    msb: int | None = None
    lsb: int | None = None

    def __str__(self) -> str:
        if self.msb is None:
            return self.name
        if self.msb == self.lsb:
            return f"{self.name}[{self.msb}]"
        return f"{self.name}[{self.msb}:{self.lsb}]"


@dataclass
class PortDecl:
    name: str
    direction: str  # "input" | "output" | "inout"
    msb: int | None = None
    lsb: int | None = None

    @property
    def is_bus(self) -> bool:
        return self.msb is not None

    @property
    def width(self) -> int:
        if self.msb is None:
            return 1
        return abs(self.msb - self.lsb) + 1


@dataclass
class WireDecl:
    name: str
    msb: int | None = None
    lsb: int | None = None

    @property
    def is_bus(self) -> bool:
        return self.msb is not None

    @property
    def width(self) -> int:
        if self.msb is None:
            return 1
        return abs(self.msb - self.lsb) + 1


@dataclass
class Instance:
    cell_type: str
    name: str
    connections: dict[str, NetRef] = field(default_factory=dict)


@dataclass
class Assign:
    lhs: NetRef
    rhs: NetRef


@dataclass
class Module:
    name: str
    port_order: list[str] = field(default_factory=list)
    ports: dict[str, PortDecl] = field(default_factory=dict)
    wires: dict[str, WireDecl] = field(default_factory=dict)
    instances: list[Instance] = field(default_factory=list)
    assigns: list[Assign] = field(default_factory=list)

    def cell_type_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for inst in self.instances:
            counts[inst.cell_type] = counts.get(inst.cell_type, 0) + 1
        return counts

    def summary(self) -> str:
        counts = self.cell_type_counts()
        top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
        lines = [
            f"Module       : {self.name}",
            f"Ports        : {len(self.ports)}  (header order: {self.port_order})",
            f"Wires        : {len(self.wires)}",
            f"Instances    : {len(self.instances)}  ({len(counts)} unique cell types)",
            f"Assigns      : {len(self.assigns)}",
            "",
            "Top cell types:",
        ]
        for cell_type, n in top:
            lines.append(f"  {n:5d}  {cell_type}")
        return "\n".join(lines)


# Internal helper carried through the parse tree.
@dataclass
class _PortConn:
    port_name: str
    net: NetRef | None


# ---------------------------------------------------------------------------
# 2. Pyparsing grammar
# ---------------------------------------------------------------------------

# -- Punctuation (suppressed) --
LBRACE, RBRACE, LPAREN, RPAREN, LBRACK, RBRACK, SEMI, COMMA, COLON, DOT, EQ = (
    pp.Suppress.using_each("{}()[];,:.=")
)

# -- Reserved words --
MODULE, ENDMODULE, INPUT, OUTPUT, INOUT, WIRE, ASSIGN = pp.Keyword.using_each(
    ["module", "endmodule", "input", "output", "inout", "wire", "assign"]
)

# -- Identifier --
identifier = pp.Word(pp.alphas + "_", pp.alphanums + "_$").set_name("identifier")

# -- Range spec [msb:lsb] (used for declarations) --
range_spec = (
    LBRACK + ppc.integer("msb") + COLON + ppc.integer("lsb") + RBRACK
).set_name("range_spec")

# -- Bit or range select on a net reference: [N] or [N:M] --
bit_or_range = (
    LBRACK
    + ppc.integer("idx_msb")
    + pp.Optional(COLON + ppc.integer("idx_lsb"))
    + RBRACK
).set_name("bit_or_range")

# -- net_ref: identifier or identifier[bit] or identifier[msb:lsb] --
net_ref = (identifier("net_name") + pp.Optional(bit_or_range)).set_name("net_ref")


def _make_net_ref(toks: pp.ParseResults) -> NetRef:
    if "idx_msb" not in toks:
        return NetRef(name=toks.net_name)
    if "idx_lsb" in toks:
        return NetRef(name=toks.net_name, msb=toks.idx_msb, lsb=toks.idx_lsb)
    return NetRef(name=toks.net_name, msb=toks.idx_msb, lsb=toks.idx_msb)


net_ref.set_parse_action(_make_net_ref)

# -- Port direction --
direction = (INPUT | OUTPUT | INOUT).set_name("direction")

# -- Port declaration: input [3:0] a, b; --
port_decl = (
    direction("dir")
    + pp.Optional(pp.Group(range_spec)("port_range"))
    + pp.DelimitedList(identifier)("names")
    + SEMI
).set_name("port_decl")


def _make_port_decls(toks: pp.ParseResults) -> list[PortDecl]:
    msb = lsb = None
    if "port_range" in toks:
        msb = toks.port_range.msb
        lsb = toks.port_range.lsb
    return [PortDecl(name=n, direction=toks.dir, msb=msb, lsb=lsb) for n in toks.names]


port_decl.set_parse_action(_make_port_decls)

# -- Wire declaration: wire [3:0] x, y; --
wire_decl = (
    WIRE.suppress()
    + pp.Optional(pp.Group(range_spec)("wire_range"))
    + pp.DelimitedList(identifier)("names")
    + SEMI
).set_name("wire_decl")


def _make_wire_decls(toks: pp.ParseResults) -> list[WireDecl]:
    msb = lsb = None
    if "wire_range" in toks:
        msb = toks.wire_range.msb
        lsb = toks.wire_range.lsb
    return [WireDecl(name=n, msb=msb, lsb=lsb) for n in toks.names]


wire_decl.set_parse_action(_make_wire_decls)

# -- Assign statement --
assign_stmt = (ASSIGN.suppress() + net_ref + EQ + net_ref + SEMI).set_name(
    "assign_stmt"
)


def _make_assign(toks: pp.ParseResults) -> Assign:
    return Assign(lhs=toks[0], rhs=toks[1])


assign_stmt.set_parse_action(_make_assign)

# -- Port connection: .port_name(net_ref) --
port_conn = (DOT + identifier + LPAREN + pp.Optional(net_ref) + RPAREN).set_name(
    "port_conn"
)


def _make_port_conn(toks: pp.ParseResults) -> _PortConn:
    port_name = toks[0]
    net = toks[1] if len(toks) > 1 else None
    return _PortConn(port_name=port_name, net=net)


port_conn.set_parse_action(_make_port_conn)

# -- Instance: cell_type inst_name (.port(net), …); --
instance = (
    identifier("cell_type")
    + identifier("inst_name")
    + LPAREN
    + pp.Optional(pp.DelimitedList(port_conn))
    + RPAREN
    + SEMI
).set_name("instance")


def _make_instance(toks: pp.ParseResults) -> Instance:
    conns: dict[str, NetRef] = {}
    for tok in toks:
        if isinstance(tok, _PortConn) and tok.net is not None:
            conns[tok.port_name] = tok.net
    return Instance(cell_type=toks.cell_type, name=toks.inst_name, connections=conns)


instance.set_parse_action(_make_instance)

# -- Module item (with endmodule lookahead so ZeroOrMore stops cleanly) --
module_item = (
    pp.NotAny(ENDMODULE) + (port_decl | wire_decl | assign_stmt | instance)
).set_name("module_item")

# -- Module --
module_grammar = (
    MODULE.suppress()
    + identifier("mod_name")
    + LPAREN
    + pp.Optional(pp.DelimitedList(identifier))("port_list")
    + RPAREN
    + SEMI
    + pp.ZeroOrMore(module_item)
    + ENDMODULE.suppress()
).set_name("module")


def _make_module(toks: pp.ParseResults) -> Module:
    port_list = list(toks.port_list) if "port_list" in toks else []
    ports: dict[str, PortDecl] = {}
    wires: dict[str, WireDecl] = {}
    instances: list[Instance] = []
    assigns: list[Assign] = []
    for tok in toks:
        if isinstance(tok, PortDecl):
            ports[tok.name] = tok
        elif isinstance(tok, WireDecl):
            wires[tok.name] = tok
        elif isinstance(tok, Instance):
            instances.append(tok)
        elif isinstance(tok, Assign):
            assigns.append(tok)
    return Module(
        name=toks.mod_name,
        port_order=port_list,
        ports=ports,
        wires=wires,
        instances=instances,
        assigns=assigns,
    )


module_grammar.set_parse_action(_make_module)

# -- Skip comments and (* attribute *) blocks --
_attribute = pp.Regex(r"\(\*[\s\S]*?\*\)").set_name("attribute")
module_grammar.ignore(pp.cpp_style_comment)
module_grammar.ignore(_attribute)


# ---------------------------------------------------------------------------
# 3. Public API
# ---------------------------------------------------------------------------


def parse(netlist_path: str | Path) -> Module:
    """Parse a single-module gate-level Verilog netlist into a Module."""
    text = Path(netlist_path).read_text(encoding="utf-8", errors="replace")
    result = module_grammar.parse_string(text, parse_all=True)
    return result[0]


# ---------------------------------------------------------------------------
# 4. Self-test
# ---------------------------------------------------------------------------

_FIXTURE = r"""
/* Generated by some tool */
(* top = 1 *)
module test_mod(clk, a, b, y);
  // single line comment
  input clk;
  wire clk;
  input [3:0] a;
  wire  [3:0] a;
  input [3:0] b;
  wire  [3:0] b;
  output [3:0] y;
  wire   [3:0] y;
  wire n1, n2;
  /* multi
     line
     comment */
  AND2 u1 (
    .A(a[0]),
    .B(b[0]),
    .Y(n1)
  );
  OR2 u2 (.A(n1), .B(b[1]), .Y(n2));
  DFF u3 (.D(n2), .CLK(clk), .Q(y[0]));
  assign y[1] = n2;
  assign n3 = n2;
  assign y[3:2] = a[3:2];
endmodule
"""


def _run_self_tests() -> None:
    passed = 0
    failed = 0

    def check(cond: bool, msg: str) -> None:
        nonlocal passed, failed
        if cond:
            passed += 1
            print(f"  [PASS] {msg}")
        else:
            failed += 1
            print(f"  [FAIL] {msg}")

    print("netlist_parser self-test")
    print("=" * 40)

    m = module_grammar.parse_string(_FIXTURE, parse_all=True)[0]

    # Module shape
    check(m.name == "test_mod", f"module name (got {m.name!r})")
    check(
        m.port_order == ["clk", "a", "b", "y"],
        f"port order (got {m.port_order})",
    )

    # Ports
    check(set(m.ports) == {"clk", "a", "b", "y"}, "all 4 ports captured")
    check(
        m.ports["clk"].direction == "input" and m.ports["clk"].msb is None,
        "scalar input clk",
    )
    check(m.ports["a"].is_bus and m.ports["a"].width == 4, "bus input a[3:0]")
    check(m.ports["y"].direction == "output", "output direction")

    # Wires
    check(
        {"clk", "a", "b", "y", "n1", "n2"}.issubset(m.wires),
        "wire decls captured (incl. duplicates of ports)",
    )
    check(m.wires["n1"].msb is None, "scalar wire n1")
    check(m.wires["a"].width == 4, "bus wire a[3:0]")

    # Instances
    check(len(m.instances) == 3, f"3 instances (got {len(m.instances)})")
    by_name = {i.name: i for i in m.instances}
    check(by_name["u1"].cell_type == "AND2", "u1 cell type")
    check(by_name["u1"].connections["A"] == NetRef("a", 0, 0), "u1.A bit-select")
    check(by_name["u1"].connections["Y"] == NetRef("n1"), "u1.Y scalar")
    check(by_name["u3"].connections["CLK"] == NetRef("clk"), "u3.CLK scalar")

    # Assigns
    check(len(m.assigns) == 3, f"3 assigns (got {len(m.assigns)})")
    a0 = m.assigns[0]
    check(
        a0.lhs == NetRef("y", 1, 1) and a0.rhs == NetRef("n2"), "bit-select assign LHS"
    )
    a2 = m.assigns[2]
    check(a2.lhs == NetRef("y", 3, 2) and a2.rhs == NetRef("a", 3, 2), "range assign")

    # Whole-bus alias (no brackets on either side)
    m_alias = module_grammar.parse_string(
        "module m(); wire [7:0] x; wire [7:0] y; assign x = y; endmodule",
        parse_all=True,
    )[0]
    check(
        m_alias.assigns[0].lhs == NetRef("x") and m_alias.assigns[0].rhs == NetRef("y"),
        "whole-bus alias",
    )

    # Empty module body
    m_empty = module_grammar.parse_string("module empty(); endmodule", parse_all=True)[
        0
    ]
    check(
        m_empty.name == "empty" and not m_empty.ports and not m_empty.instances,
        "empty module",
    )

    print("=" * 40)
    print(f"  {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


# ---------------------------------------------------------------------------
# 5. __main__
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) == 1:
        _run_self_tests()
    elif len(sys.argv) == 2:
        m = parse(sys.argv[1])
        print(m.summary())
    elif len(sys.argv) == 3:
        m = parse(sys.argv[1])
        target = sys.argv[2]
        for inst in m.instances:
            if inst.name == target:
                print(f"Instance: {inst.name}")
                print(f"Cell type: {inst.cell_type}")
                print("Connections:")
                for port, net in inst.connections.items():
                    print(f"  .{port:<6} -> {net}")
                break
        else:
            print(f"Instance {target!r} not found.")
            matches = [i.name for i in m.instances if target in i.name]
            if matches:
                print(f"Suggestions: {matches[:8]}")
    else:
        print("Usage: netlist_parser.py [netlist.v [instance_name]]")
        sys.exit(2)
