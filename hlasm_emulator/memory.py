from .errors import ExecutionError


class Memory:
    """A flat, byte-addressable image. z/Architecture is big-endian, so
    all multi-byte accesses use big-endian byte order."""

    def __init__(self, size: int):
        if size < 0:
            raise ValueError("size must be >= 0")
        self._bytes = bytearray(size)

    def __len__(self) -> int:
        return len(self._bytes)

    def _check_range(self, address: int, length: int) -> None:
        if address < 0 or address + length > len(self._bytes):
            raise ExecutionError(
                f"memory access out of range: address={address} length={length} "
                f"image_size={len(self._bytes)}"
            )

    def read_bytes(self, address: int, length: int) -> bytes:
        self._check_range(address, length)
        return bytes(self._bytes[address : address + length])

    def write_bytes(self, address: int, data: bytes) -> None:
        self._check_range(address, len(data))
        self._bytes[address : address + len(data)] = data

    def read_byte(self, address: int) -> int:
        return self._bytes[address] if 0 <= address < len(self._bytes) else self._raise(address, 1)

    def read_uint(self, address: int, length: int) -> int:
        return int.from_bytes(self.read_bytes(address, length), "big", signed=False)

    def read_int(self, address: int, length: int) -> int:
        return int.from_bytes(self.read_bytes(address, length), "big", signed=True)

    def write_int(self, address: int, length: int, value: int) -> None:
        self.write_bytes(address, _wrap_signed(value, length).to_bytes(length, "big", signed=False))

    def _raise(self, address: int, length: int):
        self._check_range(address, length)  # always raises


def _wrap_signed(value: int, length: int) -> int:
    mask = (1 << (length * 8)) - 1
    return value & mask
