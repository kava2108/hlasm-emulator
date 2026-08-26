from hlasm_emulator.lowering import lower_source
from hlasm_emulator.interpreter import Interpreter


def run(src: str) -> Interpreter:
    interp = Interpreter(lower_source(src))
    interp.run()
    return interp


def test_unconditional_branch_skips_instruction():
    src = """\
MAIN     CSECT
         LA    1,1
         B     SKIP
         LA    1,99
SKIP     LA    2,2
         END
"""
    interp = run(src)
    assert interp.cpu.get(1) == 1
    assert interp.cpu.get(2) == 2


def test_bc_extended_mnemonic_be_taken_on_equal():
    src = """\
MAIN     CSECT
         LA    1,5
         LA    2,5
         CR    1,2
         BE    EQUAL
         LA    3,0
         B     DONE
EQUAL    LA    3,1
DONE     LTR   3,3
         END
"""
    interp = run(src)
    assert interp.cpu.get(3) == 1


def test_bc_extended_mnemonic_bne_not_taken_on_equal():
    src = """\
MAIN     CSECT
         LA    1,5
         LA    2,5
         CR    1,2
         BNE   NOTEQ
         LA    3,1
         B     DONE
NOTEQ    LA    3,0
DONE     LTR   3,3
         END
"""
    interp = run(src)
    assert interp.cpu.get(3) == 1


def test_bct_loop_counts_down_to_zero():
    src = """\
MAIN     CSECT
         LA    1,3
         LA    2,0
LOOP     LA    3,1
         AR    2,3
         BCT   1,LOOP
         END
"""
    interp = run(src)
    assert interp.cpu.get(1) == 0
    assert interp.cpu.get(2) == 3


def test_bal_stores_return_index_and_jumps():
    src = """\
MAIN     CSECT
         B     START
SUB      LA    1,1
         BR    14
START    BAL   14,SUB
         LTR   1,1
         END
"""
    interp = run(src)
    assert interp.cpu.get(1) == 1


def test_balr_link_only_idiom_does_not_branch():
    src = """\
MAIN     CSECT
         BALR  12,0
         LA    1,7
         END
"""
    interp = run(src)
    assert interp.cpu.get(1) == 7
    assert interp.cpu.get(12) == 1  # linked to the IR index of the LA instruction
