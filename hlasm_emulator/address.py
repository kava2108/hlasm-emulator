"""Parsing of register operands and the ``D(P,B)`` / ``D(B)`` address
syntax shared by RX/SI/SS instruction formats. What the middle parenthesized
value (index register, or length) means is decided by the caller in
lowering.py -- this module only knows the generic ``D(p1[,p2])`` shape.
"""
import re

_ADDR_RE = re.compile(r"^(-?\d+)\(([^()]*)\)$")


def parse_address_operand(raw: str) -> tuple[int, "int | None", int]:
    """Parse ``D(B)`` or ``D(P,B)``, returning ``(D, P_or_None, B)``.

    Raises ValueError if `raw` isn't in this shape (e.g. it's a bare
    symbol or a plain number -- callers handle those separately).
    """
    m = _ADDR_RE.match(raw.strip())
    if not m:
        raise ValueError(f"not a D(...) address operand: {raw!r}")
    displacement = int(m.group(1))
    inner = m.group(2).strip()
    if inner == "":
        raise ValueError(f"address operand has no base register: {raw!r}")
    parts = [p.strip() for p in inner.split(",")]
    if len(parts) == 1:
        return displacement, None, _parse_reg_number(parts[0])
    if len(parts) == 2:
        return displacement, _parse_reg_number(parts[0]), _parse_reg_number(parts[1])
    raise ValueError(f"too many components in address operand: {raw!r}")


def parse_register_operand(raw: str) -> int:
    """Parse a bare register operand such as ``3`` or ``R3``."""
    text = raw.strip()
    if text.upper().startswith("R") and text[1:].isdigit():
        text = text[1:]
    return _parse_reg_number(text)


def _parse_reg_number(text: str) -> int:
    text = text.strip()
    if text.upper().startswith("R") and text[1:].isdigit():
        text = text[1:]
    if not text.lstrip("-").isdigit():
        raise ValueError(f"not a register number: {text!r}")
    num = int(text)
    if not (0 <= num <= 15):
        raise ValueError(f"register number out of range 0-15: {num}")
    return num
