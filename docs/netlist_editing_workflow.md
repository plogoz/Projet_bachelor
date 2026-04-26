# Netlist Editing Workflow — Full Report

## 1. Problem Statement

A hardware design requires post-synthesis netlist modifications to address signal integrity issues. The modifications are **not functional** — they do not change the logic behavior of the circuit. Instead, they involve inserting black-box elements at regular intervals (every N gate-level instances) throughout the netlist.

The closed-source EDA flow used for the real design has a 40-minute simulation cycle, making iterative development of the insertion script impractical. This report describes a parallel open-source workflow for fast prototyping and learning, with the goal of transferring the final tool to the closed-source flow.

### Constraints

- The insertion element is a **black box** — its internals are irrelevant to the script.
- The parameter **N** (insert every N elements) must be configurable at runtime.
- The netlist is **hierarchical**, but editing only happens at the **gate level** (subcircuit internals are not modified).
- The tool must be **PDK-independent** — same script for open-source and closed-source flows.
- Scale: small circuits for testing, thousands of gates (possibly more) in production.

---

## 2. Key Decision: Edit at Verilog Level

Two netlist formats were considered:

| Aspect              | Verilog Netlist                        | SPICE Netlist                          |
|---------------------|----------------------------------------|----------------------------------------|
| Format              | Structural, hierarchical, clean        | Flat or hierarchical, more verbose     |
| Parsing             | Well-defined syntax, regular structure | More irregular                         |
| PDK dependence      | Cell names change, structure doesn't   | Transistor-level, PDK-specific         |
| Transferability     | High — same logic across flows         | Flow-specific                          |
| Downstream          | Feeds into PnR tools                   | Final simulation input                 |

**Decision: edit the Verilog netlist.** The structure is identical across tools and PDKs, making the Python script portable. The modified Verilog netlist then flows through the standard synthesis/PnR/extraction pipeline normally.

---

## 3. Overall Workflow

```
┌─────────────────────────────────────────────┐
│  VHDL FSM (written by hand)                 │
│  Entity: flip_flop_adder                    │
│  File: fsm.vhdl                             │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│  YOSYS + GHDL Plugin                        │
│  Synthesizes VHDL → gate-level Verilog      │
│  (generic cells for now, sky130 later)      │
│  Output: fsm_netlist.v                      │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│  PYTHON SCRIPT (NetworkX-based)             │
│  1. Parse Verilog netlist                   │
│  2. Build directed graph (DiGraph)          │
│  3. Visualize graph (learning/debugging)    │
│  4. Topological walk, count gates           │
│  5. Insert black box every N gates          │
│  6. Serialize modified Verilog netlist      │
│  Input param: N (configurable)              │
│  Output: fsm_netlist_modified.v             │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│  OpenROAD (via OpenLane 2, Docker)          │
│  Place & Route both original + modified     │
│  SPICE extraction                           │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│  ngspice                                    │
│  Simulate both netlists                     │
│  Compare → verify functional equivalence    │
└─────────────────────────────────────────────┘
```

---

## 4. Iteration Strategy

Not every step runs on every iteration. The development loop is layered:

### Fast loop (seconds) — run constantly
```
Edit Python script → run on Verilog netlist → inspect output / visualize graph → repeat
```

### Validation loop (occasionally, minutes)
```
Run modified netlist through OpenROAD → ngspice → confirm equivalence
```

### Final transfer (once)
```
Point Python script at closed-source Verilog netlist → run through closed-source flow (40 min)
```

---

## 5. Tools

### 5.1 GHDL — VHDL Compiler

- **Purpose:** Analyze and elaborate the VHDL design.
- **Install:** `brew install ghdl`
- **Status:** Installed and working.
- **Usage (standalone simulation):**
  ```bash
  ghdl -a --std=08 fsm.vhdl
  ghdl -a --std=08 tb_flip_flop_adder.vhdl
  ghdl -e --std=08 tb_flip_flop_adder
  ghdl -r --std=08 tb_flip_flop_adder --vcd=tb.vcd
  ```

### 5.2 Yosys + GHDL Plugin — Synthesis

- **Purpose:** Synthesize VHDL into a gate-level Verilog netlist.
- **Install:** `brew install yosys` + build `ghdl-yosys-plugin` from source.
- **Status:** Installed and working (`yosys -m ghdl` loads successfully).
- **Usage (generic synthesis, no PDK):**
  ```bash
  yosys -m ghdl -p "\
      ghdl --std=08 fsm.vhdl -e flip_flop_adder; \
      synth -top flip_flop_adder; \
      write_verilog fsm_netlist.v"
  ```
- **Usage (sky130-mapped synthesis, for later):**
  ```bash
  yosys -m ghdl -p "\
      ghdl --std=08 fsm.vhdl -e flip_flop_adder; \
      synth -top flip_flop_adder; \
      dfflibmap -liberty sky130_fd_sc_hd__tt_025C_1v80.lib; \
      abc -liberty sky130_fd_sc_hd__tt_025C_1v80.lib; \
      write_verilog fsm_netlist.v; \
      write_spice fsm_netlist.spice"
  ```

### 5.3 Python + NetworkX — Netlist Editing Tool

- **Purpose:** Parse, visualize, modify, and re-serialize Verilog netlists.
- **Install:** `pip install networkx`
- **Visualization options:** Graphviz (static, small circuits), yEd via GraphML export (interactive, medium circuits), or browser-based (Cytoscape.js / d3.js).
- **Architecture:**
  ```
  parser.py       — Verilog netlist → NetworkX DiGraph
  visualizer.py   — DiGraph → visual graph output
  inserter.py     — walk graph, inject black boxes every N gates
  serializer.py   — DiGraph → Verilog netlist
  main.py         — orchestrates the above, takes N as input
  ```

### 5.4 OpenLane 2 (wraps OpenROAD + sky130 PDK) — Place & Route

- **Purpose:** Take the modified Verilog netlist through physical design and SPICE extraction.
- **Install:** Docker-based (recommended for macOS ARM).
  ```bash
  docker pull efabless/openlane2
  ```
- **PDK:** SkyWater 130nm (`sky130_fd_sc_hd`). Most mature open PDK, best community support.
- **Alternatives considered:** GlobalFoundries 180nm (gf180mcu), IHP 130nm (sg13g2).

### 5.5 ngspice — SPICE Simulation

- **Purpose:** Simulate original and modified SPICE netlists to verify functional equivalence.
- **Install:** `brew install ngspice`
- **Expected performance on small FSM:**

  | Design size   | Estimated time |
  |---------------|----------------|
  | 10–20 gates   | < 1 second     |
  | 100 gates     | a few seconds  |
  | 1,000 gates   | ~1 minute      |
  | 10,000+ gates | gets slow      |

### 5.6 Surfer — Waveform Viewer

- **Purpose:** View simulation waveforms (VCD files) from GHDL simulation.
- **Already in use.**

---

## 6. Installation Summary (macOS, M1 Max)

| Tool                | Install method       | Runs on        |
|---------------------|----------------------|----------------|
| GHDL                | `brew install ghdl`  | Native macOS   |
| Yosys               | `brew install yosys` | Native macOS   |
| ghdl-yosys-plugin   | Build from source    | Native macOS   |
| Python + NetworkX   | `pip install networkx` | Native macOS |
| ngspice             | `brew install ngspice` | Native macOS |
| OpenLane 2 / OpenROAD | Docker             | Docker container |
| sky130 PDK          | Via OpenLane or git clone | Docker / local |

---

## 7. Verilog Netlist Format Reference

### What Yosys generic synthesis produces

```verilog
module flip_flop_adder (clk, rst, A, B, Y);
  input clk, rst, A, B;
  output Y;
  wire n1, n2, n3;

  $_AND_ g1 (.A(A), .B(B), .Y(n1));
  $_OR_  g2 (.A(n1), .B(rst), .Y(n2));
  $_DFF_P_ g3 (.D(n2), .C(clk), .Q(Y));
endmodule
```

### What a closed-source tool might produce

```verilog
module flip_flop_adder (clk, rst, A, B, Y);
  input clk, rst, A, B;
  output Y;
  wire n1, n2, n3;

  AN2D1 U1 (.A1(A), .A2(B), .Z(n1));
  OR2D1 U2 (.A1(n1), .A2(rst), .Z(n2));
  DFCNQD1 U3 (.D(n2), .CP(clk), .Q(Y));
endmodule
```

Different cell names, different port names — but the **structure is identical**. The Python parser handles both by treating each instantiation line as: `cell_type instance_name (.port(net), ...)`.

---

## 8. Next Steps

1. **Run Yosys synthesis** on `fsm.vhdl` to produce the first Verilog netlist.
2. **Build the Python parser** to read the netlist into a NetworkX graph.
3. **Build a graph visualizer** to inspect and understand the circuit structure.
4. **Implement the insertion logic** (topological walk + black box injection).
5. **Validate** with OpenLane + ngspice on the small FSM.
6. **Transfer** to the closed-source Verilog netlist.
