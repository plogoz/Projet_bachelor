-- ----
-- Vibe coded w. Claude code on 16.04.2026
-- ----

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.cste.all;

-- Run with GHDL (VHDL 2008):
--   ghdl -a --std=08 fsm.vhdl
--   ghdl -a --std=08 tb_flip_flop_adder.vhdl
--   ghdl -e --std=08 tb_flip_flop_adder
--   ghdl -r --std=08 tb_flip_flop_adder --vcd=tb.vcd

entity tb_flip_flop_adder is
end entity tb_flip_flop_adder;

architecture tb of tb_flip_flop_adder is

    signal CLKxCI   : std_logic := '0';
    signal RSTxRI   : std_logic := '1';
    signal ReadAxSI : std_logic := '0';
    signal ReadBxSI : std_logic := '0';
    signal AxDI     : unsigned(NumLength-1 downto 0) := (others => '0');
    signal BxDI     : unsigned(NumLength-1 downto 0) := (others => '0');
    signal outxDO   : unsigned(NumLength-1 downto 0);

    constant CLK_PERIOD : time := 10 ns;

    procedure check(
        sig       : in unsigned(NumLength-1 downto 0);
        expected  : in natural;
        test_name : in string
    ) is
    begin
        assert to_integer(sig) = expected
            report "FAIL [" & test_name & "]: got "
                   & integer'image(to_integer(sig))
                   & ", expected " & integer'image(expected)
            severity error;
    end procedure;

begin

    dut : entity work.flip_flop_adder
        port map (
            CLKxCI   => CLKxCI,
            RSTxRI   => RSTxRI,
            ReadAxSI => ReadAxSI,
            ReadBxSI => ReadBxSI,
            AxDI     => AxDI,
            BxDI     => BxDI,
            outxDO   => outxDO
        );

    CLKxCI <= not CLKxCI after CLK_PERIOD / 2;

    stim : process is
        procedure tick is
        begin
            wait until rising_edge(CLKxCI);
            wait for 1 ns;  -- advance past all delta cycles; outputs are stable here
        end procedure;
    begin
        -- ----------------------------------------------------------------
        -- Reset
        -- ----------------------------------------------------------------
        RSTxRI <= '1';
        tick; tick;
        RSTxRI <= '0';
        tick;
        check(outxDO, 0, "output cleared after reset");

        -- ----------------------------------------------------------------
        -- Test 1: basic addition  10 + 20 = 30
        -- Cycle N  : ReadA=1, ReadB=1 → A and B latched on rising edge
        -- Cycle N+1: outxDP captures outxDN = A+B
        -- ----------------------------------------------------------------
        AxDI <= to_unsigned(10, NumLength);
        BxDI <= to_unsigned(20, NumLength);
        ReadAxSI <= '1'; ReadBxSI <= '1';
        tick;
        ReadAxSI <= '0'; ReadBxSI <= '0';
        tick;
        check(outxDO, 30, "10+20=30");

        -- ----------------------------------------------------------------
        -- Test 2: update A only — B retains its previous value (20)
        -- ----------------------------------------------------------------
        AxDI     <= to_unsigned(100, NumLength);
        ReadAxSI <= '1';
        tick;
        ReadAxSI <= '0';
        tick;
        check(outxDO, 120, "100+20=120 (A updated only)");

        -- ----------------------------------------------------------------
        -- Test 3: update B only — A retains its previous value (100)
        -- ----------------------------------------------------------------
        BxDI     <= to_unsigned(5, NumLength);
        ReadBxSI <= '1';
        tick;
        ReadBxSI <= '0';
        tick;
        check(outxDO, 105, "100+5=105 (B updated only)");

        -- ----------------------------------------------------------------
        -- Test 4: no read enables — output must be stable
        -- ----------------------------------------------------------------
        tick;
        check(outxDO, 105, "no enable, output stable");

        -- ----------------------------------------------------------------
        -- Test 5: unsigned overflow wraps modulo 2^NumLength
        -- ----------------------------------------------------------------
        AxDI <= to_unsigned(65535, NumLength);
        BxDI <= to_unsigned(1,     NumLength);
        ReadAxSI <= '1'; ReadBxSI <= '1';
        tick;
        ReadAxSI <= '0'; ReadBxSI <= '0';
        tick;
        check(outxDO, 0, "overflow 65535+1=0");

        -- ----------------------------------------------------------------
        -- Test 6: zero + zero
        -- ----------------------------------------------------------------
        AxDI <= to_unsigned(0, NumLength);
        BxDI <= to_unsigned(0, NumLength);
        ReadAxSI <= '1'; ReadBxSI <= '1';
        tick;
        ReadAxSI <= '0'; ReadBxSI <= '0';
        tick;
        check(outxDO, 0, "0+0=0");

        -- ----------------------------------------------------------------
        -- Test 7: asynchronous reset clears registers immediately
        -- Load A=42, B=58 then assert RST before the sum can propagate.
        -- ----------------------------------------------------------------
        AxDI <= to_unsigned(42, NumLength);
        BxDI <= to_unsigned(58, NumLength);
        ReadAxSI <= '1'; ReadBxSI <= '1';
        tick;                       -- A=42, B=58 latched; outxDN=100
        ReadAxSI <= '0'; ReadBxSI <= '0';
        RSTxRI   <= '1';            -- async: clears outxDP, AxDP, BxDP instantly
        wait for CLK_PERIOD / 4;
        check(outxDO, 0, "async reset clears output before next clock");
        RSTxRI <= '0';
        tick;
        check(outxDO, 0, "after reset released: A+B both 0");

        -- ----------------------------------------------------------------
        -- Test 8: large values without overflow  (32768 + 32767 = 65535)
        -- ----------------------------------------------------------------
        AxDI <= to_unsigned(32768, NumLength);
        BxDI <= to_unsigned(32767, NumLength);
        ReadAxSI <= '1'; ReadBxSI <= '1';
        tick;
        ReadAxSI <= '0'; ReadBxSI <= '0';
        tick;
        check(outxDO, 65535, "32768+32767=65535");

        report "All tests passed" severity note;
        std.env.stop(0);
    end process;

end architecture tb;
