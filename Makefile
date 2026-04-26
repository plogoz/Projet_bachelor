.PHONY: help all fsm surfer synth clean

# skywater130nm path
LIB = skywater-pdk-libs-sky130_fd_sc_hd/timing/sky130_fd_sc_hd__tt_025C_1v80.lib

help:
	@echo "=== flip_flop_adder Project ==="
	@echo ""
	@echo "Available targets:"
	@echo "  make sim       - Compile and simulate the flip-flop adder"
	@echo "  make surfer    - Open waveform viewer (requires tb.vcd)"
	@echo "  make synth     - Synthesize design to Verilog netlist"
	@echo "  make clean     - Remove generated files and artifacts"
	@echo "  make help      - Show this help message"
	@echo "  make net   - Synthesize design to Verilog netlist SkyWater130nm mapping"
	@echo ""

sim:
	ghdl -a --std=08 fsm.vhdl
	ghdl -a --std=08 tb_flip_flop_adder.vhdl
	ghdl -e --std=08 tb_flip_flop_adder
	ghdl -r --std=08 tb_flip_flop_adder --vcd=tb.vcd

surfer:
	surfer tb.vcd

synth:
	GHDL_PREFIX=/opt/homebrew/lib/ghdl yosys -m ghdl -p "\
    	ghdl --std=08 fsm.vhdl -e flip_flop_adder; \
        synth -top flip_flop_adder; \
     	write_verilog fsm_netlist.v"

net:
	GHDL_PREFIX=/opt/homebrew/lib/ghdl yosys -m ghdl -p "\
		ghdl --std=08 fsm.vhdl -e flip_flop_adder; \
		synth -top flip_flop_adder; \
		dfflibmap -liberty $(LIB); \
		abc -liberty $(LIB); \
		write_verilog fsm_netlist.v"

clean:
	rm -f *.o *.cf *.vcd
	rm -f tb_flip_flop_adder
	rm -f fsm_netlist.v
	@echo "Cleaned: object files, config files, waveforms, testbench, and synthesis results"
