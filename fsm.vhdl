-- ----
-- * Testfile for netlist editing through OSS EDA tools (Bachelor project)
-- * Philippe Logoz 26.04.2026
-- ----

library ieee;
use ieee.std_logic_1164.all;

package cste is

    constant NumLength : natural := 16;

end cste;

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.cste.all;

entity flip_flop_adder is
    port (
    CLKxCI : in std_logic;
    RSTxRI : in std_logic;

    -- control signals
    ReadAxSI : in std_logic;
    ReadBxSI : in std_logic;

    -- data signals
    AxDI : in unsigned(NumLength-1 downto 0);
    BxDI : in unsigned(NumLength-1 downto 0);
    outxDO : out unsigned(NumLength-1 downto 0)
    );
end flip_flop_adder ;

architecture rtl of flip_flop_adder is

    signal AxDP: unsigned(NumLength-1 downto 0);
    signal BxDP: unsigned(NumLength-1 downto 0);
    signal outxDP, outxDN : unsigned(NumLength-1 downto 0);

begin

    adder_fsm : process(CLKxCI, RSTxRI) is
    begin
        if(RSTxRI = '1') then
            outxDP <= (others => '0');
        elsif rising_edge(CLKxCI) then
            outxDP <= outxDN;
        end if;
    end process;

    A_flip_flop : process(CLKxCI, RSTxRI) is
    begin
        if(RSTxRI = '1') then
            AxDP <= (others => '0');
        elsif rising_edge(CLKxCI) then
            if ReadAxSI = '1' then
                AxDP <= AxDI;
            end if;
        end if;
    end process;

    B_flip_flop : process(CLKxCI, RSTxRI) is
    begin
        if(RSTxRI = '1') then
            BxDP <= (others => '0');
        elsif rising_edge(CLKxCI) then
            if ReadBxSI = '1' then
                BxDP <= BxDI;
            end if;
        end if;
    end process;

    outxDN <= AxDP + BxDP;
    outxDO <= outxDP;

end rtl;
