import sys

from .protocol import DAPReader, DAPWriter
from .server import DebugSession


def main() -> int:
    reader = DAPReader(sys.stdin.buffer)
    writer = DAPWriter(sys.stdout.buffer)
    DebugSession(reader, writer).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
