from dataclasses import dataclass


@dataclass(frozen=True)
class AddressRef:
    """An effective-address computation: displacement + GPR(base) +
    GPR(index). ``base_reg == 0`` with ``index_reg == 0`` also covers a
    bare data-label symbol resolved directly to an absolute address at
    lowering time (see lowering.py) -- displacement then holds that
    absolute address."""

    displacement: int
    base_reg: int = 0
    index_reg: int = 0

    def resolve(self, cpu) -> int:
        base = cpu.get(self.base_reg) if self.base_reg else 0
        index = cpu.get(self.index_reg) if self.index_reg else 0
        return self.displacement + base + index


@dataclass(frozen=True)
class RR:
    r1: int
    r2: int


@dataclass(frozen=True)
class RX:
    r1: int
    addr: AddressRef


@dataclass(frozen=True)
class SI:
    addr: AddressRef
    imm: int


@dataclass(frozen=True)
class SS:
    dest: AddressRef
    length: int
    src: AddressRef


@dataclass(frozen=True)
class BranchAlways:
    target_index: int


@dataclass(frozen=True)
class BranchMasked:
    mask: int
    target_index: int


@dataclass(frozen=True)
class BranchReg:
    reg: int


@dataclass(frozen=True)
class BranchCount:
    r1: int
    target_index: int


@dataclass(frozen=True)
class BranchCountReg:
    r1: int
    r2: int


@dataclass(frozen=True)
class BranchLink:
    r1: int
    target_index: int


@dataclass(frozen=True)
class BranchLinkReg:
    r1: int
    r2: int


@dataclass(frozen=True)
class IRInstruction:
    index: int
    mnemonic: str
    args: object
    line_no: int
    label: "str | None" = None
