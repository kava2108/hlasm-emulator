import argparse
import sys

from .interpreter import Interpreter
from .lowering import lower_source


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="hlasm-emulator")
    parser.add_argument("source", help="path to an HLASM source file")
    parser.add_argument(
        "--trace", action="store_true", help="print a register dump after every step"
    )
    parser.add_argument(
        "--max-steps", type=int, default=1_000_000, help="abort if execution doesn't halt by then"
    )
    args = parser.parse_args(argv)

    with open(args.source, encoding="utf-8") as f:
        text = f.read()

    lowered = lower_source(text)
    interp = Interpreter(lowered)

    if args.trace:
        while interp.cpu.running:
            instr = interp.current_instruction
            label = f"{instr.label}: " if instr and instr.label else ""
            if instr:
                print(f"[{instr.index}] {label}{instr.mnemonic}")
            interp.step()
            print(f"  {interp.last_explanation}")
            print(interp.register_dump())
            print()
    else:
        interp.run(max_steps=args.max_steps)

    print("=== final state ===")
    print(interp.register_dump())
    return 0


if __name__ == "__main__":
    sys.exit(main())
