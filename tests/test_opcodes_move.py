from hlasm_emulator.lowering import lower_source
from hlasm_emulator.interpreter import Interpreter


def run(src: str) -> Interpreter:
    interp = Interpreter(lower_source(src))
    interp.run()
    return interp


def test_l_and_st_roundtrip():
    src = """\
MAIN     CSECT
         L     1,SRC
         ST    1,DST
         END
SRC      DC    F'42'
DST      DC    F'0'
"""
    interp = run(src)
    addr = interp.data_labels["DST"]
    assert interp.memory.read_int(addr, 4) == 42


def test_mvi_writes_one_byte():
    src = """\
MAIN     CSECT
         MVI   FLAG,C'Y'
         END
FLAG     DC    C' '
"""
    interp = run(src)
    addr = interp.data_labels["FLAG"]
    assert interp.memory.read_bytes(addr, 1) == "Y".encode("cp037")


def test_mvc_uses_implied_length_from_symbol():
    src = """\
MAIN     CSECT
         MVC   DST,SRC
         END
SRC      DC    CL5'HELLO'
DST      DC    CL5'     '
"""
    interp = run(src)
    addr = interp.data_labels["DST"]
    assert interp.memory.read_bytes(addr, 5) == "HELLO".encode("cp037")


def test_clc_sets_cc_equal():
    src = """\
MAIN     CSECT
         CLC   A,B
         END
A        DC    CL3'ABC'
B        DC    CL3'ABC'
"""
    interp = run(src)
    assert interp.cpu.psw.condition_code == 0


def test_la_loads_data_address():
    src = """\
MAIN     CSECT
         LA    3,DATA
         END
DATA     DC    F'7'
"""
    interp = run(src)
    assert interp.cpu.get(3) == interp.data_labels["DATA"]
