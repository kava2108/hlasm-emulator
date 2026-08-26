import pytest

from hlasm_emulator.errors import ExecutionError
from hlasm_emulator.interpreter import Interpreter
from hlasm_emulator.lowering import lower_source


def run(src: str) -> Interpreter:
    interp = Interpreter(lower_source(src))
    interp.run()
    return interp


def test_cvb_converts_packed_decimal_to_binary():
    src = """\
MAIN     CSECT
         CVB   1,PACKED
         END
PACKED   DC    PL8'12345'
"""
    interp = run(src)
    assert interp.cpu.get_signed(1) == 12345


def test_cvb_negative():
    src = """\
MAIN     CSECT
         CVB   1,PACKED
         END
PACKED   DC    PL8'-42'
"""
    interp = run(src)
    assert interp.cpu.get_signed(1) == -42


def test_cvd_converts_binary_to_packed_decimal():
    src = """\
MAIN     CSECT
         LA    1,678
         CVD   1,OUT
         END
OUT      DS    PL8
"""
    interp = run(src)
    addr = interp.data_labels["OUT"]
    raw = interp.memory.read_bytes(addr, 8)
    assert len(raw) == 8
    assert raw[-1] & 0x0F == 0xC  # positive sign nibble
    from hlasm_emulator.packed_decimal import decode_packed

    assert decode_packed(raw) == 678


def test_cvb_cvd_round_trip():
    src = """\
MAIN     CSECT
         LA    1,987654
         CVD   1,TEMP
         CVB   2,TEMP
         END
TEMP     DS    PL8
"""
    interp = run(src)
    assert interp.cpu.get_signed(2) == 987654


def test_mr_multiplies_into_register_pair():
    src = """\
MAIN     CSECT
         LA    5,7
         LA    3,6
         MR    4,3
         END
"""
    interp = run(src)
    assert interp.cpu.get_signed(4) == 0
    assert interp.cpu.get_signed(5) == 42


def test_mr_requires_even_register():
    src = """\
MAIN     CSECT
         LA    5,7
         LA    3,6
         MR    5,3
         END
"""
    with pytest.raises(ExecutionError):
        run(src)


def test_dr_divides_register_pair():
    src = """\
MAIN     CSECT
         LA    4,0
         LA    5,17
         LA    3,5
         DR    4,3
         END
"""
    interp = run(src)
    assert interp.cpu.get_signed(5) == 3  # quotient
    assert interp.cpu.get_signed(4) == 2  # remainder


def test_dr_truncates_toward_zero_for_negative_dividend():
    src = """\
MAIN     CSECT
         L     4,NEGONE
         L     5,NEG17
         LA    3,5
         DR    4,3
         END
NEGONE   DC    F'-1'
NEG17    DC    F'-17'
"""
    interp = run(src)
    # dividend pair = (R4 sign-extended, R5) = -17, divisor = 5
    # -> quotient -3, remainder -2 (remainder sign matches dividend, truncated toward zero)
    assert interp.cpu.get_signed(5) == -3
    assert interp.cpu.get_signed(4) == -2


def test_dr_by_zero_raises():
    src = """\
MAIN     CSECT
         LA    4,0
         LA    5,17
         LA    3,0
         DR    4,3
         END
"""
    with pytest.raises(ExecutionError):
        run(src)


def test_nr_or_xr():
    src = """\
MAIN     CSECT
         LA    1,12
         LA    2,10
         NR    1,2
         END
"""
    interp = run(src)
    assert interp.cpu.get(1) == 12 & 10
    assert interp.cpu.psw.condition_code == 1


def test_nr_zero_result_sets_cc0():
    src = """\
MAIN     CSECT
         LA    1,12
         LA    2,3
         NR    1,2
         END
"""
    interp = run(src)
    assert interp.cpu.get(1) == 0
    assert interp.cpu.psw.condition_code == 0


def test_or_and_x_register_forms():
    src = """\
MAIN     CSECT
         LA    1,12
         LA    2,3
         OR    1,2
         LA    3,5
         XR    1,3
         END
"""
    interp = run(src)
    assert interp.cpu.get(1) == (12 | 3) ^ 5


def test_n_o_x_memory_forms():
    src = """\
MAIN     CSECT
         LA    1,255
         N     1,MASK
         END
MASK     DC    F'15'
"""
    interp = run(src)
    assert interp.cpu.get(1) == 255 & 15


def test_lm_stm_round_trip_with_wraparound():
    src = """\
MAIN     CSECT
         LA    14,111
         LA    15,222
         LA    0,333
         STM   14,0,SAVE
         LA    14,0
         LA    15,0
         LA    0,0
         LM    14,0,SAVE
         END
SAVE     DS    3F
"""
    interp = run(src)
    assert interp.cpu.get(14) == 111
    assert interp.cpu.get(15) == 222
    assert interp.cpu.get(0) == 333
