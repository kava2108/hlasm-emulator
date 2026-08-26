from hlasm_emulator.interpreter import Interpreter
from hlasm_emulator.lowering import lower_source


def step_n(src: str, n: int) -> Interpreter:
    interp = Interpreter(lower_source(src))
    for _ in range(n):
        interp.step()
    return interp


def test_ar_explanation():
    src = """\
MAIN     CSECT
         LA    1,5
         LA    2,3
         AR    1,2
         END
"""
    interp = step_n(src, 3)
    assert interp.last_explanation == "R1 = R1 + R2 = 5 + 3 = 8; CC=2"


def test_sr_negative_explanation():
    src = """\
MAIN     CSECT
         LA    1,3
         LA    2,5
         SR    1,2
         END
"""
    interp = step_n(src, 3)
    assert interp.last_explanation == "R1 = R1 - R2 = 3 - 5 = -2; CC=1"


def test_lr_explanation():
    src = """\
MAIN     CSECT
         LA    1,7
         LR    2,1
         END
"""
    interp = step_n(src, 2)
    assert interp.last_explanation == "R2 = R1 = 7"


def test_ltr_explanation():
    src = """\
MAIN     CSECT
         LA    1,0
         LTR   2,1
         END
"""
    interp = step_n(src, 2)
    assert interp.last_explanation == "R2 = R1 = 0; CC=0"


def test_cr_explanation():
    src = """\
MAIN     CSECT
         LA    1,5
         LA    2,5
         CR    1,2
         END
"""
    interp = step_n(src, 3)
    assert interp.last_explanation == "compare R1, R2: 5 vs 5; CC=0"


def test_la_explanation():
    src = """\
MAIN     CSECT
         LA    3,DATA
         END
DATA     DC    F'7'
"""
    interp = step_n(src, 1)
    addr = interp.data_labels["DATA"]
    assert interp.last_explanation == f"R3 = address {addr} (0x{addr:X})"


def test_l_and_st_explanation():
    src = """\
MAIN     CSECT
         L     1,SRC
         ST    1,DST
         END
SRC      DC    F'42'
DST      DC    F'0'
"""
    interp = step_n(src, 1)
    src_addr = interp.data_labels["SRC"]
    assert interp.last_explanation == f"R1 = mem[{src_addr}] = 42"

    interp.step()
    dst_addr = interp.data_labels["DST"]
    assert interp.last_explanation == f"mem[{dst_addr}] = R1 = 42"


def test_a_explanation():
    src = """\
MAIN     CSECT
         LA    1,10
         A     1,FIVE
         END
FIVE     DC    F'5'
"""
    interp = step_n(src, 2)
    addr = interp.data_labels["FIVE"]
    assert interp.last_explanation == f"R1 = R1 + mem[{addr}] = 10 + 5 = 15; CC=2"


def test_c_explanation():
    src = """\
MAIN     CSECT
         LA    1,5
         C     1,FIVE
         END
FIVE     DC    F'5'
"""
    interp = step_n(src, 2)
    addr = interp.data_labels["FIVE"]
    assert interp.last_explanation == f"compare R1, mem[{addr}]: 5 vs 5; CC=0"


def test_mvi_explanation():
    src = """\
MAIN     CSECT
         MVI   FLAG,X'FF'
         END
FLAG     DC    C' '
"""
    interp = step_n(src, 1)
    addr = interp.data_labels["FLAG"]
    assert interp.last_explanation == f"mem[{addr}] = 0xFF"


def test_mvc_explanation():
    src = """\
MAIN     CSECT
         MVC   DST,SRC
         END
SRC      DC    CL5'HELLO'
DST      DC    CL5'     '
"""
    interp = step_n(src, 1)
    src_addr = interp.data_labels["SRC"]
    dst_addr = interp.data_labels["DST"]
    expected_bytes = "HELLO".encode("cp037")
    assert interp.last_explanation == (
        f"mem[{dst_addr}..{dst_addr + 5}) = mem[{src_addr}..{src_addr + 5}) = {expected_bytes!r}"
    )


def test_clc_explanation():
    src = """\
MAIN     CSECT
         CLC   A,B
         END
A        DC    CL3'ABC'
B        DC    CL3'ABC'
"""
    interp = step_n(src, 1)
    a_addr = interp.data_labels["A"]
    b_addr = interp.data_labels["B"]
    assert interp.last_explanation == (
        f"compare mem[{a_addr}..{a_addr + 3}), mem[{b_addr}..{b_addr + 3}) (3 bytes); CC=0"
    )


def test_branch_always_explanation():
    src = """\
MAIN     CSECT
         B     SKIP
         LA    1,99
SKIP     LA    2,2
         END
"""
    interp = step_n(src, 1)
    target = interp.code_labels["SKIP"]
    assert interp.last_explanation == f"jump to #{target}"


def test_extended_branch_taken_and_not_taken():
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
    interp = step_n(src, 4)  # LA, LA, CR, BE
    target = interp.code_labels["EQUAL"]
    assert interp.last_explanation == f"BE: CC=0 -> branch to #{target}"

    src2 = src.replace("BE    EQUAL", "BNE   EQUAL")
    interp2 = step_n(src2, 4)
    assert interp2.last_explanation == "BNE: CC=0 -> fall through"


def test_bct_explanation_taken_then_not_taken():
    src = """\
MAIN     CSECT
         LA    1,2
LOOP     LA    2,0
         BCT   1,LOOP
         END
"""
    interp = step_n(src, 3)  # LA, LA, BCT (1st iteration: R1: 2->1, taken)
    loop_target = interp.code_labels["LOOP"]
    assert interp.last_explanation == f"R1 -= 1 -> 1; nonzero, branch to #{loop_target}"

    interp2 = step_n(src, 5)  # LA,LA,BCT,LA,BCT (2nd BCT: R1: 1->0, not taken)
    assert interp2.last_explanation == "R1 -= 1 -> 0; zero, fall through"


def test_br_explanation_and_r2_zero_suppression():
    src = """\
MAIN     CSECT
         B     START
SUB      LA    1,1
         BR    14
START    BAL   14,SUB
         LTR   1,1
         END
"""
    interp = step_n(src, 3)  # B, BAL(sets R14), LA -> next is BR
    interp.step()  # BR 14
    expected_target = interp.code_labels["START"] + 1  # BAL's return address (index+1)
    assert interp.last_explanation == f"BR: jump to #{expected_target} (address held in R14)"


def test_bal_and_balr_explanation():
    src = """\
MAIN     CSECT
         BAL   14,SUB
         LTR   1,1
SUB      LTR   2,2
         END
"""
    interp = step_n(src, 1)  # BAL 14,SUB
    sub_target = interp.code_labels["SUB"]
    assert interp.last_explanation == f"R14 = #1 (return address); jump to #{sub_target}"


def test_balr_link_only_explanation():
    src = """\
MAIN     CSECT
         BALR  12,0
         LA    1,7
         END
"""
    interp = step_n(src, 1)
    assert interp.last_explanation == "R12 = #1 (return address); R2 field is 0, branch suppressed"
