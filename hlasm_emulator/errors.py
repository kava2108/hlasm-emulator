class EmulatorError(Exception):
    """Base class for all errors raised by the emulator."""


class LoweringError(EmulatorError):
    """The parsed Program could not be lowered into executable IR."""


class UnsupportedInstructionError(EmulatorError):
    """The mnemonic has no execution semantics implemented yet.

    Raised (rather than silently treated as a no-op) so that an
    unsupported instruction fails loudly instead of producing a
    silently-wrong register/memory state.
    """


class ExecutionError(EmulatorError):
    """Something went wrong while executing an already-lowered instruction
    (e.g. an out-of-range register, a memory access outside the image)."""
