import pytest

from hlasm_emulator.errors import LoweringError, UnsupportedInstructionError
from hlasm_emulator.interpreter import Interpreter
from hlasm_emulator.lowering import lower_source


def test_sum_array_loop_end_to_end():
    """Sums COUNT F'0' elements starting at LIST into TOTAL -- the same
    kind of small loop hlasm-parser's own CFG examples use, run for real
    this time instead of just statically analyzed."""
    src = """\
MAIN     CSECT
         LA    4,LIST
         L     3,COUNT
         LA    2,0
LOOP     L     1,0(0,4)
         AR    2,1
         LA    4,4(0,4)
         BCT   3,LOOP
         ST    2,TOTAL
         END
COUNT    DC    F'4'
LIST     DC    F'10'
         DC    F'20'
         DC    F'30'
         DC    F'40'
TOTAL    DC    F'0'
"""
    lowered = lower_source(src)
    interp = Interpreter(lowered)
    interp.run()

    total_addr = interp.data_labels["TOTAL"]
    assert interp.memory.read_int(total_addr, 4) == 100
    assert interp.cpu.get(3) == 0
    assert not interp.cpu.running
    assert interp.cpu.halt_reason == "end of program"


def test_unimplemented_mnemonic_raises_loudly():
    src = """\
MAIN     CSECT
         MP    1,2
         END
"""
    with pytest.raises(UnsupportedInstructionError):
        lower_source(src)


def test_multi_csect_is_rejected():
    src = """\
FIRST    CSECT
         LA    1,1
SECOND   CSECT
         LA    2,2
         END
"""
    with pytest.raises(LoweringError):
        lower_source(src)


def test_unresolved_branch_target_raises():
    src = """\
MAIN     CSECT
         B     NOPE
         END
"""
    with pytest.raises(LoweringError):
        lower_source(src)
