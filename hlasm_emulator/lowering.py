"""Lowering: hlasm_parser.Program -> (list[IRInstruction], Memory).

Two deliberate v0 simplifications (see HANDOVER.md §7 follow-up notes):

1. Only single-CSECT programs are supported -- hlasm-parser doesn't
   compute cross-section link-edit addresses, so there's no principled
   way to lay out more than one section in one address space here.
2. There is no base-register/USING address arithmetic for symbolic
   operands: a bare symbol naming a DC/DS item resolves directly to that
   item's absolute offset in the emulator's memory image, bypassing the
   base register entirely. Explicit D(X,B) / D(L,B) forms still go
   through the stated base register at *run time*, so BALR-established
   base registers and manual displacement arithmetic work as expected --
   only the "let USING pick my base/displacement for a symbol" step is
   skipped, since hlasm-parser doesn't resolve USING ranges.

A label used as a branch target must sit on an executable instruction
statement, not on a DC/DS statement (the common "LOOP DS 0H" alignment
idiom is not supported as a branch target).
"""
from dataclasses import dataclass

import hlasm_parser as hp
from hlasm_parser.layout import compute_layout

from . import ir
from .address import parse_address_operand, parse_register_operand
from .branch_masks import EXTENDED_BRANCH_MASK
from .dc_values import encode_dc_operand
from .errors import LoweringError, UnsupportedInstructionError
from .memory import Memory

RR_MNEMONICS = {"LR", "AR", "SR", "CR", "LTR"}
RX_MNEMONICS = {"LA", "L", "ST", "A", "S", "C"}
SI_MNEMONICS = {"MVI"}
SS_MNEMONICS = {"MVC", "CLC"}
BRANCH_ALWAYS_MNEMONICS = {"B"}
BRANCH_REG_MNEMONICS = {"BR"}
BC_MNEMONICS = {"BC"}
EXTENDED_BRANCH_MNEMONICS = set(EXTENDED_BRANCH_MASK)
BCT_MNEMONICS = {"BCT"}
BCTR_MNEMONICS = {"BCTR"}
BAL_MNEMONICS = {"BAL"}
BALR_MNEMONICS = {"BALR"}

SUPPORTED_MNEMONICS = (
    RR_MNEMONICS
    | RX_MNEMONICS
    | SI_MNEMONICS
    | SS_MNEMONICS
    | BRANCH_ALWAYS_MNEMONICS
    | BRANCH_REG_MNEMONICS
    | BC_MNEMONICS
    | EXTENDED_BRANCH_MNEMONICS
    | BCT_MNEMONICS
    | BCTR_MNEMONICS
    | BAL_MNEMONICS
    | BALR_MNEMONICS
)

# Directives that carry no run-time instruction semantics of their own.
# DC/DS are handled separately (they contribute to the memory layout, not
# to the executable instruction stream).
NON_EXECUTABLE_DIRECTIVES = {
    "CSECT", "DSECT", "START", "END", "EQU", "USING", "DROP", "DC", "DS",
    "TITLE", "PRINT", "EJECT", "SPACE", "COPY", "MACRO", "MEND", "MNOTE",
    "AMODE", "RMODE", "LTORG", "COM",
}


@dataclass
class LoweredProgram:
    instructions: list
    memory: Memory
    code_labels: dict
    data_labels: dict
    data_lengths: dict


def lower_source(text: str, **parse_kwargs) -> LoweredProgram:
    program = hp.parse(text, **parse_kwargs)
    return lower_program(program)


def lower_program(program) -> LoweredProgram:
    if len(program.sections) != 1:
        raise LoweringError(
            "only single-CSECT programs are supported "
            f"(got {len(program.sections)} sections)"
        )
    section = program.sections[0]

    memory, data_labels, data_lengths = _build_memory(section)
    instructions, code_labels = _lower_instructions(section, data_labels, data_lengths)
    return LoweredProgram(instructions, memory, code_labels, data_labels, data_lengths)


def _build_memory(section):
    layout = compute_layout(section)
    size = max((item.offset + item.length for item in layout if item.offset is not None and item.length), default=0)
    memory = Memory(size)
    data_labels: dict = {}
    data_lengths: dict = {}

    statements_by_line = {stmt.line_no: stmt for stmt in section.statements}

    for item in layout:
        if item.label:
            data_labels[item.label] = item.offset
            data_lengths[item.label] = item.length
        if item.operation == "DC" and item.offset is not None and item.length:
            stmt = statements_by_line[item.line_no]
            operand_index = 0 if item.label else _operand_index(stmt, item)
            operand = stmt.operands[operand_index]
            data = encode_dc_operand(operand.raw, item.length, item.dup)
            memory.write_bytes(item.offset, data)

    return memory, data_labels, data_lengths


def _operand_index(stmt, item) -> int:
    for i, operand in enumerate(stmt.operands):
        if operand.raw == item.operand:
            return i
    raise LoweringError(f"could not locate operand {item.operand!r} on line {item.line_no}")


def _lower_instructions(section, data_labels, data_lengths):
    executable = []
    code_labels: dict = {}
    for stmt in section.statements:
        op = (stmt.operation or "").upper()
        if op in NON_EXECUTABLE_DIRECTIVES:
            continue
        if op not in SUPPORTED_MNEMONICS:
            raise UnsupportedInstructionError(
                f"line {stmt.line_no}: mnemonic {stmt.operation!r} is not implemented"
            )
        if stmt.label:
            code_labels[stmt.label] = len(executable)
        executable.append(stmt)

    instructions = []
    for index, stmt in enumerate(executable):
        args = _resolve_operands(index, stmt, code_labels, data_labels, data_lengths)
        instructions.append(
            ir.IRInstruction(
                index=index,
                mnemonic=stmt.operation.upper(),
                args=args,
                line_no=stmt.line_no,
                label=stmt.label,
            )
        )
    return instructions, code_labels


def _resolve_operands(index, stmt, code_labels, data_labels, data_lengths):
    op = stmt.operation.upper()
    operands = stmt.operands
    try:
        if op in RR_MNEMONICS:
            _expect(operands, 2, op, stmt)
            r1 = parse_register_operand(operands[0].raw)
            r2 = parse_register_operand(operands[1].raw)
            return ir.RR(r1, r2)

        if op in RX_MNEMONICS:
            _expect(operands, 2, op, stmt)
            r1 = parse_register_operand(operands[0].raw)
            addr = _resolve_rx_address(operands[1].raw, data_labels, code_labels)
            return ir.RX(r1, addr)

        if op in SI_MNEMONICS:
            _expect(operands, 2, op, stmt)
            addr = _resolve_plain_address(operands[0].raw, data_labels)
            from .dc_values import parse_self_defining_byte

            imm = parse_self_defining_byte(operands[1].raw)
            return ir.SI(addr, imm)

        if op in SS_MNEMONICS:
            _expect(operands, 2, op, stmt)
            dest, length = _resolve_ss_dest(operands[0].raw, data_labels, data_lengths)
            src = _resolve_plain_address(operands[1].raw, data_labels)
            return ir.SS(dest, length, src)

        if op in BRANCH_ALWAYS_MNEMONICS:
            _expect(operands, 1, op, stmt)
            target = _resolve_branch_target(operands[0].raw, code_labels)
            return ir.BranchAlways(target)

        if op in BRANCH_REG_MNEMONICS:
            _expect(operands, 1, op, stmt)
            reg = parse_register_operand(operands[0].raw)
            return ir.BranchReg(reg)

        if op in BC_MNEMONICS:
            _expect(operands, 2, op, stmt)
            mask = int(operands[0].raw.strip())
            target = _resolve_branch_target(operands[1].raw, code_labels)
            return ir.BranchMasked(mask, target)

        if op in EXTENDED_BRANCH_MNEMONICS:
            _expect(operands, 1, op, stmt)
            mask = EXTENDED_BRANCH_MASK[op]
            target = _resolve_branch_target(operands[0].raw, code_labels)
            return ir.BranchMasked(mask, target)

        if op in BCT_MNEMONICS:
            _expect(operands, 2, op, stmt)
            r1 = parse_register_operand(operands[0].raw)
            target = _resolve_branch_target(operands[1].raw, code_labels)
            return ir.BranchCount(r1, target)

        if op in BCTR_MNEMONICS:
            _expect(operands, 2, op, stmt)
            r1 = parse_register_operand(operands[0].raw)
            r2 = parse_register_operand(operands[1].raw)
            return ir.BranchCountReg(r1, r2)

        if op in BAL_MNEMONICS:
            _expect(operands, 2, op, stmt)
            r1 = parse_register_operand(operands[0].raw)
            target = _resolve_branch_target(operands[1].raw, code_labels)
            return ir.BranchLink(r1, target)

        if op in BALR_MNEMONICS:
            _expect(operands, 2, op, stmt)
            r1 = parse_register_operand(operands[0].raw)
            r2 = parse_register_operand(operands[1].raw)
            return ir.BranchLinkReg(r1, r2)
    except (ValueError, LoweringError) as exc:
        raise LoweringError(f"line {stmt.line_no} ({op}): {exc}") from exc

    raise UnsupportedInstructionError(f"line {stmt.line_no}: mnemonic {op!r} is not implemented")


def _expect(operands, count, op, stmt):
    if len(operands) != count:
        raise LoweringError(
            f"line {stmt.line_no}: {op} expects {count} operand(s), got {len(operands)}"
        )


def _resolve_rx_address(raw, data_labels, code_labels) -> ir.AddressRef:
    raw = raw.strip()
    if raw in data_labels:
        return ir.AddressRef(displacement=data_labels[raw])
    if raw in code_labels:
        raise LoweringError(f"code label {raw!r} cannot be used as a data address")
    if raw.lstrip("-").isdigit():
        return ir.AddressRef(displacement=int(raw))
    d, x, b = parse_address_operand(raw)
    return ir.AddressRef(displacement=d, base_reg=b, index_reg=x or 0)


def _resolve_plain_address(raw, data_labels) -> ir.AddressRef:
    """D(B) address, or a bare data-label symbol -- used by SI addresses
    and by the second (source) operand of SS instructions, neither of
    which take an index register."""
    raw = raw.strip()
    if raw in data_labels:
        return ir.AddressRef(displacement=data_labels[raw])
    if raw.lstrip("-").isdigit():
        return ir.AddressRef(displacement=int(raw))
    d, mid, b = parse_address_operand(raw)
    if mid is not None:
        raise LoweringError(f"address {raw!r} must not have an index register")
    return ir.AddressRef(displacement=d, base_reg=b)


def _resolve_ss_dest(raw, data_labels, data_lengths) -> tuple:
    raw = raw.strip()
    if raw in data_labels:
        length = data_lengths.get(raw)
        if not length:
            raise LoweringError(f"symbol {raw!r} has no known storage length for an SS instruction")
        return ir.AddressRef(displacement=data_labels[raw]), length
    d, length, b = parse_address_operand(raw)
    if length is None:
        raise LoweringError(
            f"SS destination {raw!r} needs an explicit length D(L,B), or use a symbolic operand"
        )
    return ir.AddressRef(displacement=d, base_reg=b), length


def _resolve_branch_target(raw, code_labels) -> int:
    raw = raw.strip()
    if raw not in code_labels:
        raise LoweringError(
            f"branch target {raw!r} is not a label on an executable instruction"
        )
    return code_labels[raw]
