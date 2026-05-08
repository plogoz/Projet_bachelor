.PHONY: help sim surfer synth net editing visualize spice clean

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
	@echo "  make spice     - Convert Verilog netlists to SPICE (requires net + editing)"
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

# read_liberty loads cell port order so write_spice produces non-empty output.
# -neg/-pos map the power net names to sky130 conventions.
spice: fsm_netlist.spice fsm_modified.spice

fsm_netlist.spice: fsm_netlist.v
	yosys -p "\
		read_liberty -ignore_miss_func $(LIB); \
		read_verilog $<; \
		write_spice $@"

fsm_modified.spice: fsm_modified.v
	yosys -p "\
		read_liberty -ignore_miss_func $(LIB); \
		read_verilog -lib $<; \
		write_spice $@"

clean:
	rm -f *.o *.cf *.vcd *.sp *.spice
	rm -f tb_flip_flop_adder
	rm -f fsm_netlist.v fsm_modified.v
	@echo "Cleaned: object files, config files, waveforms, testbench, and synthesis results"
