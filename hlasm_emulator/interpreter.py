from dataclasses import dataclass

from . import ir
from .cpu import CPU
from .errors import ExecutionError
from .explain import explain
from .opcodes import execute


@dataclass(frozen=True)
class CallFrame:
    """One pending BAL/BALR call, for the debugger's call-stack display
    only -- the interpreter itself has no notion of a "call", just
    branches (see the module docstring below for how this is inferred)."""

    call_instr: object  # the IRInstruction that performed the call
    target_index: int  # where it jumped to (the callee's entry point)
    return_index: int  # the IR index execution resumes at on return


class Interpreter:
    """Steps a lowered program.

    ``call_stack`` is a heuristic, debugger-facing reconstruction of
    "which subroutine calls are pending": whenever a BAL/BALR actually
    branches, that's treated as a call and pushed; whenever some later
    branch's target exactly matches the return address on top of the
    stack, that's treated as the matching return and popped. Real
    hardware has no call stack -- BAL/BALR/BR are just branches that
    happen to be used in a call/return convention -- so this only works
    for programs that follow that convention (call via BAL/BALR, return
    via a branch straight to the saved return address). A subroutine
    that never returns, or that returns via some other mechanism, simply
    leaves stale frames on this stack; that's a display quirk, not a
    correctness issue, since nothing else in the emulator reads it.
    """

    def __init__(self, lowered):
        self.instructions = lowered.instructions
        self.memory = lowered.memory
        self.code_labels = lowered.code_labels
        self.data_labels = lowered.data_labels
        self.data_lengths = lowered.data_lengths
        self.cpu = CPU()
        self.last_explanation = ""
        self.call_stack: list = []

    @property
    def current_instruction(self):
        ip = self.cpu.psw.instruction_address
        if 0 <= ip < len(self.instructions):
            return self.instructions[ip]
        return None

    def step(self) -> None:
        """Execute exactly one IR instruction. Halts the CPU (rather than
        raising) once the instruction pointer runs off the end of the
        program, which is how a program without an explicit halt/loop
        "finishes" in this emulator."""
        if not self.cpu.running:
            return
        instr = self.current_instruction
        if instr is None:
            self.cpu.halt("end of program")
            return
        before_gpr = list(self.cpu.gpr)
        next_ip = execute(self.cpu, self.memory, instr)
        next_ip = next_ip if next_ip is not None else instr.index + 1
        self.last_explanation = explain(instr, before_gpr, self.cpu, self.memory, next_ip)
        self._update_call_stack(instr, next_ip)
        self.cpu.psw.instruction_address = next_ip

    def _update_call_stack(self, instr, next_ip: int) -> None:
        branched = next_ip != instr.index + 1
        if branched and isinstance(instr.args, (ir.BranchLink, ir.BranchLinkReg)):
            self.call_stack.append(CallFrame(instr, next_ip, instr.index + 1))
        elif self.call_stack and next_ip == self.call_stack[-1].return_index:
            self.call_stack.pop()

    def run(self, max_steps: int = 1_000_000) -> None:
        steps = 0
        while self.cpu.running:
            if steps >= max_steps:
                raise ExecutionError(f"exceeded max_steps={max_steps} without halting")
            self.step()
            steps += 1

    def register_dump(self) -> str:
        gpr = self.cpu.gpr
        lines = []
        for row in range(4):
            cells = [f"R{row * 4 + col:<2}={gpr[row * 4 + col]:08X}" for col in range(4)]
            lines.append("  ".join(cells))
        lines.append(
            f"IP={self.cpu.psw.instruction_address}  CC={self.cpu.psw.condition_code}  "
            f"running={self.cpu.running}"
            + (f"  halt_reason={self.cpu.halt_reason!r}" if self.cpu.halt_reason else "")
        )
        return "\n".join(lines)
