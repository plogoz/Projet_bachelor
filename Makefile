.PHONY: help sim surfer synth net editing visualize verify clean all

# skywater130nm path
LIB = skywater-pdk-libs-sky130_fd_sc_hd/timing/sky130_fd_sc_hd__tt_025C_1v80.lib

N_BUFF = 5

help:
	@echo "=== flip_flop_adder Project ==="
	@echo ""
	@echo "Available targets:"
	@echo ""
	@echo "  make sim       - Compile and simulate the flip-flop adder"
	@echo "  make surfer    - Open waveform viewer (requires tb.vcd)"
	@echo "  make synth     - Synthesize design to Verilog netlist (generic cells)"
	@echo "  make net       - Synthesize design to Verilog netlist (SkyWater130nm)"
	@echo "  make editing   - Edit the netlist with the netlist_tool"
	@echo "  make visualize - Visualize the netlist with the netlist_tool"
	@echo "  make verify    - Prove fsm_modified.v is logically equivalent to fsm_netlist.v"
	@echo "  make all       - Clean, synthesize, and verify the design"
	@echo "  make clean     - Remove generated files and artifacts"
	@echo "  make help      - Show this help message"
	@echo ""

sim:
	ghdl -a --std=08 fsm.vhdl
	ghdl -a --std=08 tb_flip_flop_adder.vhdl
	ghdl -e --std=08 tb_flip_flop_adder
	ghdl -r --std=08 tb_flip_flop_adder --vcd=tb.vcd

surfer:
	surfer tb.vcd

synth: # generic library synthesis
	GHDL_PREFIX=/opt/homebrew/lib/ghdl yosys -m ghdl -p "\
    	ghdl --std=08 fsm.vhdl -e flip_flop_adder; \
        synth -top flip_flop_adder; \
     	write_verilog fsm_netlist.v"

net: # synthesis with SkyWater130nm mapping
	GHDL_PREFIX=/opt/homebrew/lib/ghdl yosys -m ghdl -p "\
		ghdl --std=08 fsm.vhdl -e flip_flop_adder; \
		synth -top flip_flop_adder; \
		dfflibmap -liberty $(LIB); \
		abc -liberty $(LIB); \
		write_verilog fsm_netlist.v"

editing:
	uv run python -m netlist_tool fsm_netlist.v fsm_modified.v --N $(N_BUFF) --lib $(LIB)

visualize:
	uv run python -m netlist_tool fsm_netlist.v fsm_modified.v --N $(N_BUFF) --visualize

# Formal equivalence check: prove fsm_modified.v == fsm_netlist.v.
# Buffer insertion preserves logic, so equiv_induct should converge instantly.
verify: fsm_netlist.v fsm_modified.v
	yosys -p "\
		read_liberty -ignore_miss_func $(LIB); \
		read_verilog fsm_netlist.v; \
		rename flip_flop_adder gold; \
		read_verilog fsm_modified.v; \
		rename flip_flop_adder gate; \
		equiv_make gold gate equiv; \
		hierarchy -top equiv; \
		clk2fflogic; \
		async2sync; \
		prep -flatten; \
		equiv_induct -seq 10; \
		equiv_status -assert"

all : clean net editing verify

clean:
	rm -f *.o *.cf *.vcd
	rm -f tb_flip_flop_adder
	rm -f fsm_netlist.v fsm_modified.v
	@echo "Cleaned: object files, config files, waveforms, testbench, and synthesis results"
