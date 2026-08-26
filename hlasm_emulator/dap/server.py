"""A minimal Debug Adapter Protocol server driving hlasm_emulator's
Interpreter. Single-threaded and synchronous: `continue` runs the
interpreter loop in-process until a breakpoint, program end, or a step
ceiling is hit, then replies -- there's no real concurrency to manage
since instruction execution never blocks on I/O.

Known v0 limitations (see HANDOVER.md):
- One thread, one stack frame (no call-stack tracking beyond BAL/BALR's
  link register, so stepIn/stepOut behave the same as a single step).
- `pause` is a no-op affordance: since `continue` is synchronous, there's
  nothing running to interrupt when a pause request could be processed.
- No conditional/hit-count breakpoints, no watch/data breakpoints, no
  `readMemory`/`writeMemory` requests -- only line breakpoints and
  register/data-label inspection via `evaluate` and `variables`.
"""
import os
import re

from ..errors import EmulatorError
from ..interpreter import Interpreter
from ..lowering import lower_source

REGISTERS_REF = 1
DATA_REF = 2

_REGISTER_RE = re.compile(r"^[Rr](\d{1,2})$")

MAX_CONTINUE_STEPS = 5_000_000


class DebugSession:
    def __init__(self, reader, writer):
        self._reader = reader
        self._writer = writer
        self._seq = 1
        self._alive = True

        self.interp: "Interpreter | None" = None
        self.source_path: "str | None" = None
        self.breakpoint_lines: set = set()
        self.line_to_index: dict = {}
        self.stop_on_entry = True

    # ── transport helpers ────────────────────────────────────────────

    def _next_seq(self) -> int:
        seq = self._seq
        self._seq += 1
        return seq

    def send_event(self, event: str, body: dict = None) -> None:
        msg = {"seq": self._next_seq(), "type": "event", "event": event}
        if body is not None:
            msg["body"] = body
        self._writer.write_message(msg)

    def send_response(self, request: dict, success: bool = True, body: dict = None, message: str = None) -> None:
        msg = {
            "seq": self._next_seq(),
            "type": "response",
            "request_seq": request["seq"],
            "success": success,
            "command": request["command"],
        }
        if body is not None:
            msg["body"] = body
        if message is not None:
            msg["message"] = message
        self._writer.write_message(msg)

    def send_output(self, text: str, category: str = "console") -> None:
        self.send_event("output", {"category": category, "output": text})

    # ── main loop ────────────────────────────────────────────────────

    def run(self) -> None:
        while self._alive:
            message = self._reader.read_message()
            if message is None:
                break
            if message.get("type") == "request":
                self.handle_request(message)

    def handle_request(self, request: dict) -> None:
        command = request["command"]
        handler = getattr(self, f"cmd_{command}", None)
        if handler is None:
            self.send_response(request, success=False, message=f"unsupported command: {command}")
            return
        try:
            handler(request)
        except EmulatorError as exc:
            self.send_response(request, success=False, message=str(exc))
            self.send_output(f"{command} failed: {exc}\n", category="stderr")
        except Exception as exc:  # unexpected bug -- still report, don't crash the session
            self.send_response(request, success=False, message=f"internal error: {exc}")
            self.send_output(f"{command} raised {exc!r}\n", category="stderr")

    # ── lifecycle commands ───────────────────────────────────────────

    def cmd_initialize(self, request: dict) -> None:
        self.send_response(request, body={
            "supportsConfigurationDoneRequest": True,
            "supportsEvaluateForHovers": True,
            "supportsTerminateRequest": True,
            "supportsFunctionBreakpoints": False,
            "supportsConditionalBreakpoints": False,
            "supportsHitConditionalBreakpoints": False,
            "supportsStepBack": False,
            "exceptionBreakpointFilters": [],
        })
        self.send_event("initialized")

    def cmd_launch(self, request: dict) -> None:
        args = request.get("arguments", {})
        program = args["program"]
        self.stop_on_entry = bool(args.get("stopOnEntry", True))
        self.source_path = program

        with open(program, encoding="utf-8") as f:
            text = f.read()
        lowered = lower_source(text)
        self.interp = Interpreter(lowered)
        self.line_to_index = {}
        for instr in self.interp.instructions:
            self.line_to_index.setdefault(instr.line_no, instr.index)

        self.send_response(request)

    def cmd_setBreakpoints(self, request: dict) -> None:
        args = request["arguments"]
        requested = args.get("breakpoints", [])
        resolved = []
        self.breakpoint_lines = set()
        for bp in requested:
            requested_line = bp["line"]
            actual_line = self._snap_to_executable_line(requested_line)
            if actual_line is not None:
                self.breakpoint_lines.add(actual_line)
                resolved.append({"verified": True, "line": actual_line})
            else:
                resolved.append({
                    "verified": False,
                    "line": requested_line,
                    "message": "no executable instruction at or after this line",
                })
        self.send_response(request, body={"breakpoints": resolved})

    def cmd_setExceptionBreakpoints(self, request: dict) -> None:
        self.send_response(request, body={"breakpoints": []})

    def cmd_setFunctionBreakpoints(self, request: dict) -> None:
        self.send_response(request, body={"breakpoints": []})

    def cmd_configurationDone(self, request: dict) -> None:
        self.send_response(request)
        if self.stop_on_entry:
            self.send_event("stopped", {"reason": "entry", "threadId": 1})
        else:
            self._continue_execution()

    def _snap_to_executable_line(self, requested_line: int):
        candidates = sorted(line for line in self.line_to_index if line >= requested_line)
        return candidates[0] if candidates else None

    # ── execution state inspection ───────────────────────────────────

    def cmd_threads(self, request: dict) -> None:
        self.send_response(request, body={"threads": [{"id": 1, "name": "main"}]})

    def cmd_stackTrace(self, request: dict) -> None:
        instr = self.interp.current_instruction if self.interp else None
        if instr is None:
            frames = []
        else:
            label_prefix = f"{instr.label}: " if instr.label else ""
            frames = [{
                "id": 1,
                "name": f"{label_prefix}{instr.mnemonic}",
                "line": instr.line_no,
                "column": 1,
                "source": {"path": self.source_path, "name": os.path.basename(self.source_path)},
            }]
        self.send_response(request, body={"stackFrames": frames, "totalFrames": len(frames)})

    def cmd_scopes(self, request: dict) -> None:
        self.send_response(request, body={
            "scopes": [
                {"name": "Registers", "variablesReference": REGISTERS_REF, "expensive": False},
                {"name": "Data", "variablesReference": DATA_REF, "expensive": False},
            ]
        })

    def cmd_variables(self, request: dict) -> None:
        ref = request["arguments"]["variablesReference"]
        if ref == REGISTERS_REF:
            variables = self._register_variables()
        elif ref == DATA_REF:
            variables = self._data_variables()
        else:
            variables = []
        self.send_response(request, body={"variables": variables})

    def _register_variables(self) -> list:
        cpu = self.interp.cpu
        variables = [
            {"name": f"R{i}", "value": _format_word(cpu.get(i)), "variablesReference": 0}
            for i in range(16)
        ]
        variables.append({"name": "CC", "value": str(cpu.psw.condition_code), "variablesReference": 0})
        variables.append({"name": "IP", "value": str(cpu.psw.instruction_address), "variablesReference": 0})
        variables.append({
            "name": "(last step)",
            "value": self.interp.last_explanation or "(not started)",
            "variablesReference": 0,
        })
        return variables

    def _data_variables(self) -> list:
        out = []
        for label, addr in sorted(self.interp.data_labels.items(), key=lambda kv: kv[1]):
            out.append({"name": label, "value": self._format_data_label(label), "variablesReference": 0})
        return out

    def _format_data_label(self, label: str) -> str:
        addr = self.interp.data_labels[label]
        length = self.interp.data_lengths.get(label, 0)
        if length in (1, 2, 4, 8):
            return _format_word(self.interp.memory.read_int(addr, length), length)
        if length:
            return self.interp.memory.read_bytes(addr, length).hex().upper()
        return "<no storage>"

    # ── execution control ────────────────────────────────────────────

    def cmd_continue(self, request: dict) -> None:
        self.send_response(request, body={"allThreadsContinued": True})
        self._continue_execution()

    def cmd_next(self, request: dict) -> None:
        self._single_step(request)

    # No real call-stack tracking (see module docstring) -- step in/out
    # degrade to a plain single step, which is at least never wrong.
    cmd_stepIn = cmd_next
    cmd_stepOut = cmd_next

    def cmd_pause(self, request: dict) -> None:
        self.send_response(request)
        self.send_event("stopped", {"reason": "pause", "threadId": 1})

    def cmd_disconnect(self, request: dict) -> None:
        self.send_response(request)
        self._alive = False

    def cmd_terminate(self, request: dict) -> None:
        self.send_response(request)
        self.send_event("terminated")
        self._alive = False

    def _single_step(self, request: dict) -> None:
        self.send_response(request)
        if self.interp.cpu.running:
            self.interp.step()
            self.send_output(f"{self.interp.last_explanation}\n")
        if self.interp.cpu.running:
            self.send_event("stopped", {"reason": "step", "threadId": 1})
        else:
            self.send_event("terminated")

    def _continue_execution(self) -> None:
        # `instr is not None` guards the case where the instruction pointer
        # has run off the end of the program: self.interp.step() handles
        # that by halting the CPU itself (see Interpreter.step), which is
        # what actually flips cpu.running and ends the while loop below --
        # this function must never decide "the program is over" on its own.
        first = True
        steps = 0
        while self.interp.cpu.running:
            instr = self.interp.current_instruction
            if instr is not None and not first and instr.line_no in self.breakpoint_lines:
                self.send_event("stopped", {"reason": "breakpoint", "threadId": 1})
                return
            first = False
            self.interp.step()
            self.send_output(f"{self.interp.last_explanation}\n")
            steps += 1
            if steps >= MAX_CONTINUE_STEPS:
                self.send_output(f"stopped after {steps} steps without halting (possible infinite loop)\n")
                self.send_event("stopped", {"reason": "pause", "threadId": 1})
                return
        self.send_event("terminated")

    # ── evaluate (watch / hover) ─────────────────────────────────────

    def cmd_evaluate(self, request: dict) -> None:
        expr = request["arguments"]["expression"].strip()
        result = self._evaluate(expr)
        if result is None:
            self.send_response(request, success=False, message=f"cannot evaluate: {expr!r}")
        else:
            self.send_response(request, body={"result": result, "variablesReference": 0})

    def _evaluate(self, expr: str):
        cpu = self.interp.cpu
        m = _REGISTER_RE.match(expr)
        if m:
            num = int(m.group(1))
            return _format_word(cpu.get(num)) if 0 <= num <= 15 else None
        if expr.upper() == "CC":
            return str(cpu.psw.condition_code)
        if expr.upper() == "IP":
            return str(cpu.psw.instruction_address)
        if expr in self.interp.data_labels:
            return self._format_data_label(expr)
        return None


def _format_word(value: int, length: int = 4) -> str:
    width = length * 2
    return f"{value} (0x{value & ((1 << (length * 8)) - 1):0{width}X})"
