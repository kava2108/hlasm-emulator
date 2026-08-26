"""Human-readable, per-step descriptions of what an instruction just did,
e.g. "R2 = R2 + R1 = 0 + 10 = 10". Purely a diagnostic/UX aid consumed by
the CLI's --trace flag and the DAP server (stack frame name + Debug
Console output) -- it has no bearing on execution semantics, which live
entirely in opcodes.py. Kept in its own module so formatting concerns
don't bloat the opcode dispatch table, and dispatches on the IR argument
*type* (RR/RX/SI/SS/branch shapes) rather than one function per mnemonic,
since same-shaped instructions share almost all of their formatting.

Coverage is expected to be complete for every mnemonic lowering.py
accepts; an unhandled shape falls back to the bare mnemonic rather than
raising, since a missing explanation is a cosmetic gap, not a correctness
bug.
"""
from . import ir
from .cpu import CPU

_ARITH_OP = {"AR": "+", "A": "+", "SR": "-", "S": "-"}


def explain(instr, before_gpr: list, cpu, memory, next_ip: int) -> str:
    """`before_gpr` is a snapshot of cpu.gpr taken immediately before this
    instruction executed; `cpu`/`memory` reflect the state immediately
    after. `next_ip` is what the interpreter is about to set
    cpu.psw.instruction_address to (used to detect whether a branch was
    taken)."""
    before = CPU(gpr=list(before_gpr))
    args = instr.args
    m = instr.mnemonic

    if isinstance(args, ir.RR):
        return _explain_rr(m, args, before, cpu)
    if isinstance(args, ir.RX):
        return _explain_rx(m, args, before, cpu, memory)
    if isinstance(args, ir.SI):
        return _explain_si(args, before, memory)
    if isinstance(args, ir.SS):
        return _explain_ss(m, args, before, cpu, memory)

    taken = next_ip != instr.index + 1
    if isinstance(args, ir.BranchAlways):
        return f"jump to #{args.target_index}"
    if isinstance(args, ir.BranchMasked):
        cc = cpu.psw.condition_code
        outcome = f"branch to #{args.target_index}" if taken else "fall through"
        return f"{m}: CC={cc} -> {outcome}"
    if isinstance(args, ir.BranchReg):
        if args.reg == 0:
            return f"{m}: R2 field is 0, branch suppressed"
        return f"{m}: jump to #{next_ip} (address held in R{args.reg})"
    if isinstance(args, ir.BranchCount):
        value = cpu.get_signed(args.r1)
        outcome = f"nonzero, branch to #{args.target_index}" if taken else "zero, fall through"
        return f"R{args.r1} -= 1 -> {value}; {outcome}"
    if isinstance(args, ir.BranchCountReg):
        value = cpu.get_signed(args.r1)
        if args.r2 == 0:
            return f"R{args.r1} -= 1 -> {value}; R2 field is 0, branch suppressed"
        outcome = f"nonzero, jump to #{next_ip}" if taken else "zero, fall through"
        return f"R{args.r1} -= 1 -> {value}; {outcome}"
    if isinstance(args, ir.BranchLink):
        return f"R{args.r1} = #{instr.index + 1} (return address); jump to #{args.target_index}"
    if isinstance(args, ir.BranchLinkReg):
        link = f"R{args.r1} = #{instr.index + 1} (return address)"
        if args.r2 == 0:
            return f"{link}; R2 field is 0, branch suppressed"
        return f"{link}; jump to #{next_ip}"

    return m  # pragma: no cover - every lowerable mnemonic shape is handled above


def _explain_rr(m: str, args: ir.RR, before: CPU, cpu) -> str:
    r1, r2 = args.r1, args.r2
    if m == "LR":
        return f"R{r1} = R{r2} = {cpu.get_signed(r1)}"
    if m == "LTR":
        return f"R{r1} = R{r2} = {cpu.get_signed(r1)}; CC={cpu.psw.condition_code}"
    if m in _ARITH_OP:
        op = _ARITH_OP[m]
        a, b = before.get_signed(r1), before.get_signed(r2)
        return f"R{r1} = R{r1} {op} R{r2} = {a} {op} {b} = {cpu.get_signed(r1)}; CC={cpu.psw.condition_code}"
    if m == "CR":
        a, b = before.get_signed(r1), before.get_signed(r2)
        return f"compare R{r1}, R{r2}: {a} vs {b}; CC={cpu.psw.condition_code}"
    return m


def _explain_rx(m: str, args: ir.RX, before: CPU, cpu, memory) -> str:
    r1 = args.r1
    addr = args.addr.resolve(before)
    if m == "LA":
        return f"R{r1} = address {addr} (0x{addr:X})"
    if m == "L":
        return f"R{r1} = mem[{addr}] = {cpu.get_signed(r1)}"
    if m == "ST":
        return f"mem[{addr}] = R{r1} = {cpu.get_signed(r1)}"
    if m in _ARITH_OP:
        op = _ARITH_OP[m]
        a, b = before.get_signed(r1), memory.read_int(addr, 4)
        return f"R{r1} = R{r1} {op} mem[{addr}] = {a} {op} {b} = {cpu.get_signed(r1)}; CC={cpu.psw.condition_code}"
    if m == "C":
        a, b = before.get_signed(r1), memory.read_int(addr, 4)
        return f"compare R{r1}, mem[{addr}]: {a} vs {b}; CC={cpu.psw.condition_code}"
    return m


def _explain_si(args: ir.SI, before: CPU, memory) -> str:
    addr = args.addr.resolve(before)
    return f"mem[{addr}] = 0x{args.imm:02X}"


def _explain_ss(m: str, args: ir.SS, before: CPU, cpu, memory) -> str:
    dest = args.dest.resolve(before)
    src = args.src.resolve(before)
    span = f"[{dest}..{dest + args.length})"
    src_span = f"[{src}..{src + args.length})"
    if m == "MVC":
        return f"mem{span} = mem{src_span} = {memory.read_bytes(dest, args.length)!r}"
    if m == "CLC":
        return f"compare mem{span}, mem{src_span} ({args.length} bytes); CC={cpu.psw.condition_code}"
    return m
