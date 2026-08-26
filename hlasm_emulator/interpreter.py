from .cpu import CPU
from .errors import ExecutionError
from .opcodes import execute


class Interpreter:
    def __init__(self, lowered):
        self.instructions = lowered.instructions
        self.memory = lowered.memory
        self.code_labels = lowered.code_labels
        self.data_labels = lowered.data_labels
        self.data_lengths = lowered.data_lengths
        self.cpu = CPU()

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
        next_ip = execute(self.cpu, self.memory, instr)
        self.cpu.psw.instruction_address = (
            next_ip if next_ip is not None else instr.index + 1
        )

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
