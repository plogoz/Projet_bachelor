# Simulations

## VHDL Testbench — `tb_flip_flop_adder`

Testbench for `flip_flop_adder` (16-bit registered adder with load enables and async reset).
Written in VHDL 2008, targeting GHDL.

### Run

```sh
ghdl -a --std=08 fsm.vhdl
ghdl -a --std=08 tb_flip_flop_adder.vhdl
ghdl -e --std=08 tb_flip_flop_adder
ghdl -r --std=08 tb_flip_flop_adder --vcd=tb.vcd
```

Open the waveform with GTKWave:

```sh
gtkwave tb.vcd
```

### Test cases

| # | Scenario |
|---|----------|
| 1 | Basic addition: 10 + 20 = 30 |
| 2 | A updated only, B retained: 100 + 20 = 120 |
| 3 | B updated only, A retained: 100 + 5 = 105 |
| 4 | Neither read enable active — output stable |
| 5 | Unsigned overflow: 65535 + 1 = 0 |
| 6 | Zero + zero = 0 |
| 7 | Async reset clears registers immediately (mid-clock) |
| 8 | Large values without overflow: 32768 + 32767 = 65535 |

### Design notes

- `tick` does `wait until rising_edge` + `wait for 1 ns`. The 1 ns advances past all delta cycles so checks read stable post-edge values.
- `std.env.stop(0)` terminates the simulation cleanly with exit code 0. A non-zero exit signals test failure, making it scriptable.
- The output register has two-cycle latency: one cycle to latch A and B, one cycle to register the sum.
- The reset is asynchronous and active-high.

### Fix applied to `fsm.vhdl`

In VHDL, each design unit needs its own `library`/`use` clauses — they do not carry over from a preceding package in the same file. The entity was missing:

```vhdl
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.cste.all;
```

These were added immediately before `entity flip_flop_adder is`.

---

## Yosys Synthesis — `make synth`

### Run

```sh
make synth
```

This produces `fsm_netlist.v` (generic gate-level Verilog, no PDK mapping).

### Known issue: `cannot find "std" library`

The ghdl-yosys plugin resolves the VHDL IEEE libraries as `$GHDL_PREFIX/ieee/v08/`. Without `GHDL_PREFIX` set, the plugin falls back to a relative path baked in at build time (`../../install/lib/ghdl/...`) that does not exist on a standard Homebrew install.

**Fix:** set `GHDL_PREFIX` to the Homebrew GHDL library directory before invoking Yosys. The Makefile `synth` target already does this:

```makefile
GHDL_PREFIX=/opt/homebrew/lib/ghdl yosys -m ghdl -p "..."
```

If the error resurfaces after a `brew upgrade ghdl`, verify that `/opt/homebrew/lib/ghdl/ieee/v08/` still exists.

<!-- session : claude --resume dd5b4ab8-2920-4b71-9293-39e4d1b04635 -->
