from dataclasses import dataclass, field

WORD_BITS = 32
WORD_MASK = (1 << WORD_BITS) - 1
WORD_SIGN_BIT = 1 << (WORD_BITS - 1)


def to_unsigned32(value: int) -> int:
    return value & WORD_MASK


def to_signed32(value: int) -> int:
    value &= WORD_MASK
    return value - (1 << WORD_BITS) if value & WORD_SIGN_BIT else value


@dataclass
class PSW:
    """Simplified Program Status Word.

    ``instruction_address`` is an index into the lowered IR instruction
    list, NOT a real z/Architecture byte address -- see lowering.py for
    why (hlasm-parser doesn't compute instruction byte addresses/lengths,
    so the emulator uses IR position as its notion of "current location").
    """

    instruction_address: int = 0
    condition_code: int = 0  # 0-3


@dataclass
class CPU:
    gpr: list = field(default_factory=lambda: [0] * 16)
    psw: PSW = field(default_factory=PSW)
    running: bool = True
    halt_reason: str = ""

    def get(self, reg: int) -> int:
        """Unsigned 32-bit value of GPR(reg)."""
        self._check_reg(reg)
        return self.gpr[reg]

    def get_signed(self, reg: int) -> int:
        return to_signed32(self.get(reg))

    def set(self, reg: int, value: int) -> None:
        self._check_reg(reg)
        self.gpr[reg] = to_unsigned32(value)

    def set_cc(self, cc: int) -> None:
        assert 0 <= cc <= 3
        self.psw.condition_code = cc

    def halt(self, reason: str) -> None:
        self.running = False
        self.halt_reason = reason

    @staticmethod
    def _check_reg(reg: int) -> None:
        if not (0 <= reg <= 15):
            raise ValueError(f"invalid GPR number: {reg}")
