"""Instruction semantics: one handler per mnemonic, all sharing the
signature ``handler(cpu, memory, instr) -> int | None``.

The return value tells the interpreter what to do next: ``None`` means
"fall through to the next IR instruction", an ``int`` means "the
instruction pointer is now this IR index" (a taken branch, or BAL/BALR's
link-and-jump). Handlers never mutate ``cpu.psw.instruction_address``
directly -- that's the interpreter's job, driven by this return value.
"""
from .branch_masks import CC_BIT
from .cpu import to_signed32
from .errors import UnsupportedInstructionError


def _set_cc_arithmetic(cpu, raw_result: int) -> None:
    truncated = to_signed32(raw_result)
    if truncated != raw_result:
        cpu.set_cc(3)  # overflow
    elif truncated == 0:
        cpu.set_cc(0)
    elif truncated < 0:
        cpu.set_cc(1)
    else:
        cpu.set_cc(2)


def _set_cc_compare(cpu, a, b) -> None:
    if a == b:
        cpu.set_cc(0)
    elif a < b:
        cpu.set_cc(1)
    else:
        cpu.set_cc(2)


def op_lr(cpu, memory, instr):
    args = instr.args
    cpu.set(args.r1, cpu.get(args.r2))


def op_ltr(cpu, memory, instr):
    args = instr.args
    value = cpu.get_signed(args.r2)
    cpu.set(args.r1, value)
    _set_cc_arithmetic(cpu, value)


def op_ar(cpu, memory, instr):
    args = instr.args
    result = cpu.get_signed(args.r1) + cpu.get_signed(args.r2)
    cpu.set(args.r1, result)
    _set_cc_arithmetic(cpu, result)


def op_sr(cpu, memory, instr):
    args = instr.args
    result = cpu.get_signed(args.r1) - cpu.get_signed(args.r2)
    cpu.set(args.r1, result)
    _set_cc_arithmetic(cpu, result)


def op_cr(cpu, memory, instr):
    args = instr.args
    _set_cc_compare(cpu, cpu.get_signed(args.r1), cpu.get_signed(args.r2))


def op_la(cpu, memory, instr):
    args = instr.args
    cpu.set(args.r1, args.addr.resolve(cpu))


def op_l(cpu, memory, instr):
    args = instr.args
    addr = args.addr.resolve(cpu)
    cpu.set(args.r1, memory.read_int(addr, 4))


def op_st(cpu, memory, instr):
    args = instr.args
    addr = args.addr.resolve(cpu)
    memory.write_int(addr, 4, cpu.get_signed(args.r1))


def op_a(cpu, memory, instr):
    args = instr.args
    addr = args.addr.resolve(cpu)
    result = cpu.get_signed(args.r1) + memory.read_int(addr, 4)
    cpu.set(args.r1, result)
    _set_cc_arithmetic(cpu, result)


def op_s(cpu, memory, instr):
    args = instr.args
    addr = args.addr.resolve(cpu)
    result = cpu.get_signed(args.r1) - memory.read_int(addr, 4)
    cpu.set(args.r1, result)
    _set_cc_arithmetic(cpu, result)


def op_c(cpu, memory, instr):
    args = instr.args
    addr = args.addr.resolve(cpu)
    _set_cc_compare(cpu, cpu.get_signed(args.r1), memory.read_int(addr, 4))


def op_mvi(cpu, memory, instr):
    args = instr.args
    memory.write_bytes(args.addr.resolve(cpu), bytes([args.imm]))


def op_mvc(cpu, memory, instr):
    args = instr.args
    data = memory.read_bytes(args.src.resolve(cpu), args.length)
    memory.write_bytes(args.dest.resolve(cpu), data)


def op_clc(cpu, memory, instr):
    args = instr.args
    a = memory.read_bytes(args.dest.resolve(cpu), args.length)
    b = memory.read_bytes(args.src.resolve(cpu), args.length)
    _set_cc_compare(cpu, a, b)


def op_b(cpu, memory, instr):
    return instr.args.target_index


def op_br(cpu, memory, instr):
    reg = instr.args.reg
    if reg == 0:  # architectural rule: R2 field of 0 suppresses the branch
        return None
    return cpu.get(reg)


def op_bc(cpu, memory, instr):
    args = instr.args
    if args.mask & CC_BIT[cpu.psw.condition_code]:
        return args.target_index
    return None


def op_bct(cpu, memory, instr):
    args = instr.args
    value = to_signed32(cpu.get_signed(args.r1) - 1)
    cpu.set(args.r1, value)
    return args.target_index if value != 0 else None


def op_bctr(cpu, memory, instr):
    args = instr.args
    value = to_signed32(cpu.get_signed(args.r1) - 1)
    cpu.set(args.r1, value)
    if args.r2 == 0 or value == 0:
        return None
    return cpu.get(args.r2)


def op_bal(cpu, memory, instr):
    args = instr.args
    cpu.set(args.r1, instr.index + 1)
    return args.target_index


def op_balr(cpu, memory, instr):
    args = instr.args
    cpu.set(args.r1, instr.index + 1)
    if args.r2 == 0:
        return None
    return cpu.get(args.r2)


_BASE_HANDLERS = {
    "LR": op_lr, "LTR": op_ltr, "AR": op_ar, "SR": op_sr, "CR": op_cr,
    "LA": op_la, "L": op_l, "ST": op_st, "A": op_a, "S": op_s, "C": op_c,
    "MVI": op_mvi, "MVC": op_mvc, "CLC": op_clc,
    "B": op_b, "BR": op_br, "BC": op_bc,
    "BCT": op_bct, "BCTR": op_bctr,
    "BAL": op_bal, "BALR": op_balr,
}


def _build_dispatch_table():
    from .branch_masks import EXTENDED_BRANCH_MASK

    table = dict(_BASE_HANDLERS)
    for mnemonic in EXTENDED_BRANCH_MASK:
        table[mnemonic] = op_bc  # same semantics as BC; mask is baked into instr.args at lowering time
    return table


DISPATCH_TABLE = _build_dispatch_table()


def execute(cpu, memory, instr):
    handler = DISPATCH_TABLE.get(instr.mnemonic)
    if handler is None:
        raise UnsupportedInstructionError(f"no execution handler for mnemonic {instr.mnemonic!r}")
    return handler(cpu, memory, instr)
