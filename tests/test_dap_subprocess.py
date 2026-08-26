"""One end-to-end smoke test that actually spawns `python -m
hlasm_emulator.dap` as a subprocess and talks DAP over its real stdio,
to catch wiring bugs the in-process DebugSession tests (test_dap_server.py)
can't see -- those call handle_request() directly and never touch
protocol.py's framing or __main__.py's stream setup.
"""
import json
import subprocess
import sys

PROGRAM = """\
MAIN     CSECT
         LA    1,5
         LA    2,3
         AR    1,2
         END
"""


def _write(proc, message: dict) -> None:
    data = json.dumps(message).encode("utf-8")
    proc.stdin.write(f"Content-Length: {len(data)}\r\n\r\n".encode("ascii") + data)
    proc.stdin.flush()


def _read(proc) -> dict:
    headers = {}
    while True:
        line = proc.stdout.readline().decode("ascii")
        if line in ("\r\n", "\n"):
            break
        key, _, value = line.partition(":")
        headers[key.strip().lower()] = value.strip()
    length = int(headers["content-length"])
    return json.loads(proc.stdout.read(length).decode("utf-8"))


def test_subprocess_launch_and_step(tmp_path):
    program_path = tmp_path / "add.hlasm"
    program_path.write_text(PROGRAM)

    proc = subprocess.Popen(
        [sys.executable, "-m", "hlasm_emulator.dap"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        _write(proc, {"seq": 1, "type": "request", "command": "initialize", "arguments": {}})
        assert _read(proc)["success"] is True
        assert _read(proc)["event"] == "initialized"

        _write(proc, {
            "seq": 2, "type": "request", "command": "launch",
            "arguments": {"program": str(program_path), "stopOnEntry": True},
        })
        assert _read(proc)["success"] is True

        _write(proc, {"seq": 3, "type": "request", "command": "configurationDone", "arguments": {}})
        assert _read(proc)["success"] is True
        assert _read(proc)["body"]["reason"] == "entry"

        _write(proc, {"seq": 4, "type": "request", "command": "next", "arguments": {}})
        assert _read(proc)["success"] is True
        assert _read(proc)["body"]["reason"] == "step"

        _write(proc, {"seq": 5, "type": "request", "command": "disconnect", "arguments": {}})
        assert _read(proc)["success"] is True
    finally:
        proc.stdin.close()
        proc.wait(timeout=5)
