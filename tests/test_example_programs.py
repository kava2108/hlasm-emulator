"""Runs the example programs in examples/ end-to-end, so a later change to
instruction semantics can't silently break what ships as the "try this"
onboarding material."""
from pathlib import Path

from hlasm_emulator.interpreter import Interpreter
from hlasm_emulator.lowering import lower_source
from hlasm_emulator.packed_decimal import decode_packed

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


def run_example(name: str) -> Interpreter:
    text = (EXAMPLES_DIR / name).read_text()
    interp = Interpreter(lower_source(text))
    interp.run()
    return interp


def test_sum_loop_example():
    interp = run_example("sum_loop.hlasm")
    total_addr = interp.data_labels["TOTAL"]
    assert interp.memory.read_int(total_addr, 4) == 100


def test_stats_example():
    interp = run_example("stats.hlasm")

    sum_addr = interp.data_labels["SUM"]
    max_addr = interp.data_labels["MAX"]
    avg_addr = interp.data_labels["AVGPACK"]

    values = [12, 45, 7, 93, 28, 61]
    assert interp.memory.read_int(sum_addr, 4) == sum(values)
    assert interp.memory.read_int(max_addr, 4) == max(values)

    average = interp.cpu.get_signed(1)  # AVERAGE subroutine's result, still in R1 at the end
    assert average == sum(values) // len(values)
    assert decode_packed(interp.memory.read_bytes(avg_addr, 8)) == average

    # BAL/BR round-tripped cleanly: no call frame left pending.
    assert interp.call_stack == []
