-- SYNTAX TEST "VHDL.sublime-syntax"

architecture tmp_arc of tmp is
--           ^^^^^^^ meta.block.architecture meta.block.architecture.begin.vhdl entity.name.type.architecture.begin.vhdl
--                      ^^^ entity.name.type.entity.reference.vhdl

  signal clk : std_logic;
--^^^^^^ meta.block.signal.vhdl keyword.language.vhdl
--           ^ meta.block.signal.vhdl punctuation.vhdl
--             ^^^^^^^^^ storage.type.ieee.std_logic_1164.vhdl
  signal rst : std_logic;

  FOR ALL : my_blk
    USE ENTITY work.my_blk(rtl);

begin

  test_proc: process is
--^^^^^^^^^ meta.block.process.vhdl entity.name.section.process.begin.vhdl
--           ^^^^^^^ keyword.language.vhdl
    wait on clk until rising_edge(clk) and rst = '0' for 20 ns;
--  ^^^^ keyword.language.vhdl
--              ^^^^^ keyword.language.vhdl
--                    ^^^^^^^^^^^ support.function.ieee.std_logic_1164.vhdl
--                                     ^^^ keyword.operator.word.vhdl
--                                                   ^^^ keyword.language.vhdl
--                                                          ^^ storage.type.std.standard.vhdl
    wait for c_stim_cycle - (now - v_start_time);
--                           ^^^ storage.type.std.standard.vhdl
  end process;

  report "current time = " & time'image(now);
--       ^^^^^^^^^^^^^^^^^ string.quoted.double.vhdl
--                         ^ keyword.operator.vhdl
--                           ^^^^ storage.type.std.standard.vhdl
--                               ^^^^^^ variable.other.member.vhdl
--                                      ^^^ storage.type.std.standard.vhdl

end tmp_arc;
--  ^^^^^^^ meta.block.architecture entity.name.type.architecture.end.vhdl