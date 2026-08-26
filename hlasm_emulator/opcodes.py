"""Instruction semantics: one handler per mnemonic, all sharing the
signature ``handler(cpu, memory, instr) -> int | None``.

The return value tells the interpreter what to do next: ``None`` means
"fall through to the next IR instruction", an ``int`` means "the
instruction pointer is now this IR index" (a taken branch, or BAL/BALR's
link-and-jump). Handlers never mutate ``cpu.psw.instruction_address``
directly -- that's the interpreter's job, driven by this return value.
"""
from .branch_masks import CC_BIT
from .cpu import to_signed32, to_unsigned32
from .errors import ExecutionError, UnsupportedInstructionError
from .packed_decimal import decode_packed, encode_packed


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


def _set_cc_logical(cpu, result_unsigned: int) -> None:
    cpu.set_cc(0 if result_unsigned == 0 else 1)


def _require_even(reg: int, mnemonic: str) -> None:
    if reg % 2 != 0:
        raise ExecutionError(f"{mnemonic}: register {reg} must be even (register-pair operand)")


def _register_range(r1: int, r3: int) -> list:
    """The (possibly wrapping) register numbers R1..R3 that LM/STM touch,
    e.g. r1=14, r3=12 covers 14, 15, 0, 1, ..., 12."""
    if r1 <= r3:
        return list(range(r1, r3 + 1))
    return list(range(r1, 16)) + list(range(0, r3 + 1))


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


def op_cvb(cpu, memory, instr):
    args = instr.args
    addr = args.addr.resolve(cpu)
    value = decode_packed(memory.read_bytes(addr, 8))
    if not (-(2**31) <= value <= 2**31 - 1):
        raise ExecutionError(f"CVB: decimal value {value} does not fit in a fullword")
    cpu.set(args.r1, value)


def op_cvd(cpu, memory, instr):
    args = instr.args
    addr = args.addr.resolve(cpu)
    memory.write_bytes(addr, encode_packed(cpu.get_signed(args.r1), 8))


def _multiply(cpu, r1: int, multiplicand: int, multiplier: int) -> None:
    _require_even(r1, "M/MR")
    product = multiplicand * multiplier
    unsigned64 = product & 0xFFFFFFFFFFFFFFFF
    cpu.set(r1, (unsigned64 >> 32) & 0xFFFFFFFF)
    cpu.set(r1 + 1, unsigned64 & 0xFFFFFFFF)


def op_mr(cpu, memory, instr):
    args = instr.args
    _multiply(cpu, args.r1, cpu.get_signed(args.r1 + 1), cpu.get_signed(args.r2))


def op_m(cpu, memory, instr):
    args = instr.args
    addr = args.addr.resolve(cpu)
    _multiply(cpu, args.r1, cpu.get_signed(args.r1 + 1), memory.read_int(addr, 4))


def _divide(cpu, r1: int, divisor: int) -> None:
    _require_even(r1, "D/DR")
    if divisor == 0:
        raise ExecutionError("D/DR: division by zero")
    raw64 = (cpu.get(r1) << 32) | cpu.get(r1 + 1)
    dividend = raw64 - (1 << 64) if raw64 & (1 << 63) else raw64
    quotient = abs(dividend) // abs(divisor)
    if (dividend < 0) != (divisor < 0):
        quotient = -quotient
    remainder = dividend - quotient * divisor
    if not (-(2**31) <= quotient <= 2**31 - 1):
        raise ExecutionError(f"D/DR: quotient {quotient} does not fit in a fullword")
    cpu.set(r1, remainder)
    cpu.set(r1 + 1, quotient)


def op_dr(cpu, memory, instr):
    args = instr.args
    _divide(cpu, args.r1, cpu.get_signed(args.r2))


def op_d(cpu, memory, instr):
    args = instr.args
    addr = args.addr.resolve(cpu)
    _divide(cpu, args.r1, memory.read_int(addr, 4))


def op_nr(cpu, memory, instr):
    args = instr.args
    result = to_unsigned32(cpu.get(args.r1) & cpu.get(args.r2))
    cpu.set(args.r1, result)
    _set_cc_logical(cpu, result)


def op_or_(cpu, memory, instr):
    args = instr.args
    result = to_unsigned32(cpu.get(args.r1) | cpu.get(args.r2))
    cpu.set(args.r1, result)
    _set_cc_logical(cpu, result)


def op_xr(cpu, memory, instr):
    args = instr.args
    result = to_unsigned32(cpu.get(args.r1) ^ cpu.get(args.r2))
    cpu.set(args.r1, result)
    _set_cc_logical(cpu, result)


def op_n(cpu, memory, instr):
    args = instr.args
    addr = args.addr.resolve(cpu)
    result = to_unsigned32(cpu.get(args.r1) & memory.read_uint(addr, 4))
    cpu.set(args.r1, result)
    _set_cc_logical(cpu, result)


def op_o(cpu, memory, instr):
    args = instr.args
    addr = args.addr.resolve(cpu)
    result = to_unsigned32(cpu.get(args.r1) | memory.read_uint(addr, 4))
    cpu.set(args.r1, result)
    _set_cc_logical(cpu, result)


def op_x(cpu, memory, instr):
    args = instr.args
    addr = args.addr.resolve(cpu)
    result = to_unsigned32(cpu.get(args.r1) ^ memory.read_uint(addr, 4))
    cpu.set(args.r1, result)
    _set_cc_logical(cpu, result)


def op_lm(cpu, memory, instr):
    args = instr.args
    addr = args.addr.resolve(cpu)
    for i, reg in enumerate(_register_range(args.r1, args.r3)):
        cpu.set(reg, memory.read_int(addr + i * 4, 4))


def op_stm(cpu, memory, instr):
    args = instr.args
    addr = args.addr.resolve(cpu)
    for i, reg in enumerate(_register_range(args.r1, args.r3)):
        memory.write_int(addr + i * 4, 4, cpu.get_signed(reg))


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
    "CVB": op_cvb, "CVD": op_cvd,
    "MR": op_mr, "M": op_m, "DR": op_dr, "D": op_d,
    "NR": op_nr, "OR": op_or_, "XR": op_xr, "N": op_n, "O": op_o, "X": op_x,
    "LM": op_lm, "STM": op_stm,
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
