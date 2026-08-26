from hlasm_emulator.dap.server import DebugSession

CALL_PROGRAM = """\
MAIN     CSECT
         B     START
SUB      LA    1,1
         BR    14
START    BAL   14,SUB
         LTR   1,1
         END
"""


class FakeWriter:
    def __init__(self):
        self.messages = []

    def write_message(self, message):
        self.messages.append(message)

    def events(self, name=None):
        out = [m for m in self.messages if m["type"] == "event"]
        return [m for m in out if name is None or m["event"] == name]

    def last_response(self):
        return [m for m in self.messages if m["type"] == "response"][-1]

    def clear(self):
        self.messages.clear()


def make_session(tmp_path):
    program_path = tmp_path / "call.hlasm"
    program_path.write_text(CALL_PROGRAM)
    writer = FakeWriter()
    session = DebugSession(reader=None, writer=writer)
    session.handle_request({"seq": 1, "type": "request", "command": "initialize", "arguments": {}})
    session.handle_request({
        "seq": 2, "type": "request", "command": "launch",
        "arguments": {"program": str(program_path), "stopOnEntry": True},
    })
    session.handle_request({"seq": 3, "type": "request", "command": "configurationDone", "arguments": {}})
    return session, writer


def step(session):
    session.handle_request({"seq": 100, "type": "request", "command": "next", "arguments": {}})


def stack_trace(session, writer):
    writer.clear()
    session.handle_request({"seq": 200, "type": "request", "command": "stackTrace", "arguments": {}})
    return writer.last_response()["body"]["stackFrames"]


def test_stack_trace_has_one_frame_before_any_call(tmp_path):
    session, writer = make_session(tmp_path)
    frames = stack_trace(session, writer)
    assert len(frames) == 1
    assert frames[0]["line"] == 2  # "B START"


def test_stack_trace_gains_a_frame_after_a_call(tmp_path):
    session, writer = make_session(tmp_path)
    step(session)  # B START
    step(session)  # BAL 14,SUB -> now inside SUB

    frames = stack_trace(session, writer)
    assert len(frames) == 2
    assert frames[0]["line"] == 3  # "SUB LA 1,1" -- where we're paused now
    assert "LA" in frames[0]["name"]
    assert frames[1]["line"] == 5  # "START BAL 14,SUB" -- the call site
    assert "SUB" in frames[1]["name"]


def test_stack_trace_loses_the_frame_after_returning(tmp_path):
    session, writer = make_session(tmp_path)
    step(session)  # B START
    step(session)  # BAL 14,SUB
    step(session)  # SUB: LA 1,1
    step(session)  # BR 14 -> returns

    frames = stack_trace(session, writer)
    assert len(frames) == 1
    assert frames[0]["line"] == 6  # "LTR 1,1", right after the call site
    assert session.interp.call_stack == []


def test_step_out_runs_until_the_call_returns(tmp_path):
    session, writer = make_session(tmp_path)
    step(session)  # B START
    step(session)  # BAL 14,SUB -> inside SUB now
    assert len(session.interp.call_stack) == 1

    writer.clear()
    session.handle_request({"seq": 300, "type": "request", "command": "stepOut", "arguments": {}})
    assert session.interp.call_stack == []
    assert session.interp.cpu.psw.instruction_address == 4  # "LTR 1,1", right after the call
    assert writer.events("stopped")[-1]["body"]["reason"] == "step"


def test_step_out_with_no_pending_call_runs_to_completion(tmp_path):
    session, writer = make_session(tmp_path)
    # No call has happened yet -- stepOut at the top level should behave
    # like "run to completion" rather than a no-op single step.
    writer.clear()
    session.handle_request({"seq": 300, "type": "request", "command": "stepOut", "arguments": {}})
    assert writer.events("terminated")
    assert not session.interp.cpu.running
