"""Packed-decimal (COMP-3 style) encode/decode for CVB/CVD: two BCD digits
per byte, sign nibble in the low nibble of the last byte (0xC/0xF/0xA/0xE
positive, 0xD/0xB negative -- the same convention hlasm_parser.codec uses
for DC P encoding)."""
from .errors import ExecutionError

_POSITIVE_SIGNS = (0xC, 0xF, 0xA, 0xE)
_NEGATIVE_SIGNS = (0xD, 0xB)


def decode_packed(data: bytes) -> int:
    nibbles = []
    for b in data:
        nibbles.append((b >> 4) & 0xF)
        nibbles.append(b & 0xF)
    sign_nibble = nibbles[-1]
    digit_nibbles = nibbles[:-1]
    for n in digit_nibbles:
        if n > 9:
            raise ExecutionError(f"invalid packed-decimal digit nibble: {n:X}")
    magnitude = int("".join(str(n) for n in digit_nibbles) or "0")
    if sign_nibble in _NEGATIVE_SIGNS:
        return -magnitude
    if sign_nibble in _POSITIVE_SIGNS:
        return magnitude
    raise ExecutionError(f"invalid packed-decimal sign nibble: {sign_nibble:X}")


def encode_packed(value: int, length: int) -> bytes:
    negative = value < 0
    magnitude = abs(value)
    nibble_slots = length * 2 - 1
    digits = str(magnitude).rjust(nibble_slots, "0")
    if len(digits) > nibble_slots:
        raise ExecutionError(f"value {value} does not fit in {length} packed-decimal bytes")
    nibbles = [int(c) for c in digits] + [0xD if negative else 0xC]
    out = bytearray()
    for i in range(0, len(nibbles), 2):
        out.append((nibbles[i] << 4) | nibbles[i + 1])
    return bytes(out)
