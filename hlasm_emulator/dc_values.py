"""Encoding of DC literal values (and MVI/self-defining-term immediates)
into bytes. This intentionally covers only the common numeric/character
subset (C, X, B, F, H, FD, P) -- anything else raises LoweringError rather
than silently zero-filling memory that a later instruction might read.
"""
import re

from .errors import LoweringError
from .packed_decimal import encode_packed

ENCODING = "cp037"  # EBCDIC, matches hlasm_parser.codec's default

_VALUE_RE = re.compile(
    r"^(?:\d+)?(?P<type>[A-Za-z]{1,2})(?:[LSE]\d+)*"
    r"(?P<value>'(?:[^']|'')*'|\([^()]*\))?$",
    re.DOTALL,
)

_BINARY_TYPES = {"F": 4, "H": 2, "FD": 8}
_SUPPORTED_TYPES = {"C", "X", "B", "P", *_BINARY_TYPES}


def extract_type_and_value(raw: str) -> tuple[str, "str | None"]:
    m = _VALUE_RE.match(raw.strip())
    if not m:
        raise LoweringError(f"cannot parse DC/DS operand: {raw!r}")
    return m.group("type").upper(), m.group("value")


def encode_dc_operand(raw: str, total_length: int, dup: int) -> bytes:
    """Encode one DC operand (e.g. ``F'5'``, ``3H'0'``, ``C'AB'``) into
    exactly `total_length` bytes, using the (type, dup) already computed
    by hlasm_parser.layout.compute_layout for this operand."""
    type_code, value_text = extract_type_and_value(raw)
    if type_code not in _SUPPORTED_TYPES:
        raise LoweringError(
            f"DC type {type_code!r} is not supported by the emulator (operand: {raw!r})"
        )
    unit_len = total_length // dup if dup else total_length
    unit = _encode_unit(type_code, value_text, unit_len, raw)
    return unit * dup


def _encode_unit(type_code: str, value_text: "str | None", unit_len: int, raw: str) -> bytes:
    if value_text is None:
        return b"\x00" * unit_len
    if value_text.startswith("("):
        raise LoweringError(f"parenthesized DC values are not supported: {raw!r}")
    inner = value_text[1:-1].replace("''", "'")

    if type_code == "C":
        encoded = inner.encode(ENCODING)
    elif type_code == "X":
        digits = inner.replace(" ", "")
        if len(digits) % 2:
            digits = "0" + digits
        encoded = bytes.fromhex(digits)
    elif type_code == "B":
        encoded = int(inner, 2).to_bytes((len(inner) + 7) // 8, "big")
    elif type_code in _BINARY_TYPES:
        encoded = int(inner).to_bytes(unit_len, "big", signed=True)
    elif type_code == "P":
        encoded = encode_packed(int(inner), unit_len)
    else:  # pragma: no cover - guarded by _SUPPORTED_TYPES check above
        raise LoweringError(f"unsupported DC type {type_code!r}: {raw!r}")

    if len(encoded) > unit_len:
        raise LoweringError(f"DC value {raw!r} does not fit in {unit_len} bytes")
    if type_code == "C":
        # Character constants are left-justified, padded with trailing
        # blanks -- e.g. DC CL8'HI' is "HI" followed by 6 EBCDIC spaces,
        # not 6 leading NUL bytes.
        return encoded.ljust(unit_len, " ".encode(ENCODING))
    return encoded.rjust(unit_len, b"\x00")


def parse_self_defining_byte(raw: str) -> int:
    """Parse an immediate byte operand (MVI's I2): ``C'x'``, ``X'hh'`` or
    a plain decimal integer, returning an unsigned 0-255 value."""
    text = raw.strip()
    if text.upper().startswith("C'") and text.endswith("'"):
        inner = text[2:-1].replace("''", "'")
        encoded = inner.encode(ENCODING)
        if len(encoded) != 1:
            raise LoweringError(f"MVI immediate must be exactly one character: {raw!r}")
        return encoded[0]
    if text.upper().startswith("X'") and text.endswith("'"):
        digits = text[2:-1]
        if len(digits) != 2:
            raise LoweringError(f"MVI immediate must be exactly one byte: {raw!r}")
        return int(digits, 16)
    try:
        value = int(text)
    except ValueError as exc:
        raise LoweringError(f"cannot parse immediate operand: {raw!r}") from exc
    if not (-128 <= value <= 255):
        raise LoweringError(f"immediate value out of byte range: {raw!r}")
    return value & 0xFF
