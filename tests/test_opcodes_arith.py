from hlasm_emulator.lowering import lower_source
from hlasm_emulator.interpreter import Interpreter


def run(src: str) -> Interpreter:
    interp = Interpreter(lower_source(src))
    interp.run()
    return interp


def test_ar_sets_registers_and_cc_positive():
    src = """\
MAIN     CSECT
         LA    1,5
         LA    2,3
         AR    1,2
         END
"""
    interp = run(src)
    assert interp.cpu.get(1) == 8
    assert interp.cpu.psw.condition_code == 2  # positive result


def test_sr_zero_result_sets_cc0():
    src = """\
MAIN     CSECT
         LA    1,5
         LA    2,5
         SR    1,2
         END
"""
    interp = run(src)
    assert interp.cpu.get(1) == 0
    assert interp.cpu.psw.condition_code == 0


def test_sr_negative_result_sets_cc1():
    src = """\
MAIN     CSECT
         LA    1,3
         LA    2,5
         SR    1,2
         END
"""
    interp = run(src)
    assert interp.cpu.get_signed(1) == -2
    assert interp.cpu.psw.condition_code == 1


def test_a_reads_memory_operand():
    src = """\
MAIN     CSECT
         LA    1,10
         A     1,FIVE
         END
FIVE     DC    F'5'
"""
    interp = run(src)
    assert interp.cpu.get(1) == 15


def test_ar_overflow_sets_cc3():
    src = """\
MAIN     CSECT
         L     1,MAXPOS
         LA    2,1
         AR    1,2
         END
MAXPOS   DC    F'2147483647'
"""
    interp = run(src)
    assert interp.cpu.psw.condition_code == 3


def test_cr_and_ltr():
    src = """\
MAIN     CSECT
         LA    1,5
         LA    2,5
         CR    1,2
         END
"""
    interp = run(src)
    assert interp.cpu.psw.condition_code == 0
