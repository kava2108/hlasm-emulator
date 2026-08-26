from hlasm_emulator.interpreter import Interpreter
from hlasm_emulator.lowering import lower_source


def step_n(src: str, n: int) -> Interpreter:
    interp = Interpreter(lower_source(src))
    for _ in range(n):
        interp.step()
    return interp


SINGLE_CALL_SRC = """\
MAIN     CSECT
         B     START
SUB      LA    1,1
         BR    14
START    BAL   14,SUB
         LTR   1,1
         END
"""


def test_call_pushes_a_frame():
    interp = step_n(SINGLE_CALL_SRC, 2)  # B, BAL
    assert len(interp.call_stack) == 1
    frame = interp.call_stack[0]
    assert frame.target_index == interp.code_labels["SUB"]
    assert frame.return_index == 4  # BAL is index 3, so return is index+1


def test_return_pops_the_frame():
    interp = step_n(SINGLE_CALL_SRC, 4)  # B, BAL, LA, BR (the return)
    assert interp.call_stack == []


def test_plain_branches_do_not_affect_call_stack():
    src = """\
MAIN     CSECT
         B     SKIP
         LA    1,99
SKIP     LA    2,2
         END
"""
    interp = step_n(src, 2)
    assert interp.call_stack == []


NESTED_CALL_SRC = """\
MAIN     CSECT
         B     START
OUTER    BAL   14,INNER
         BR    13
INNER    LA    1,1
         BR    14
START    LA    13,0
         BAL   13,OUTER
         END
"""


def test_nested_calls_push_and_pop_in_lifo_order():
    interp = Interpreter(lower_source(NESTED_CALL_SRC))
    # B, START:LA, START:BAL(->OUTER)
    for _ in range(3):
        interp.step()
    assert len(interp.call_stack) == 1  # OUTER call pending

    interp.step()  # OUTER:BAL(->INNER)
    assert len(interp.call_stack) == 2  # INNER call pending on top of OUTER
    outer_frame, inner_frame = interp.call_stack
    assert outer_frame.target_index == interp.code_labels["OUTER"]
    assert inner_frame.target_index == interp.code_labels["INNER"]

    interp.step()  # INNER:LA
    interp.step()  # INNER:BR 14 -> returns to OUTER
    assert len(interp.call_stack) == 1
    assert interp.call_stack[0].target_index == interp.code_labels["OUTER"]

    interp.step()  # OUTER:BR 13 -> returns to START
    assert interp.call_stack == []
