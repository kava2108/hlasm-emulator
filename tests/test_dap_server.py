from hlasm_emulator.dap.server import DebugSession

SUM_PROGRAM = """\
MAIN     CSECT
         LA    4,LIST
         L     3,COUNT
         LA    2,0
LOOP     L     1,0(0,4)
         AR    2,1
         LA    4,4(0,4)
         BCT   3,LOOP
         ST    2,TOTAL
         END
COUNT    DC    F'4'
LIST     DC    F'10'
         DC    F'20'
         DC    F'30'
         DC    F'40'
TOTAL    DC    F'0'
"""
AR_LINE = 6  # "AR 2,1"


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


def make_session(tmp_path, stop_on_entry=False):
    program_path = tmp_path / "sum.hlasm"
    program_path.write_text(SUM_PROGRAM)
    writer = FakeWriter()
    session = DebugSession(reader=None, writer=writer)

    session.handle_request({"seq": 1, "type": "request", "command": "initialize", "arguments": {}})
    session.handle_request({
        "seq": 2, "type": "request", "command": "launch",
        "arguments": {"program": str(program_path), "stopOnEntry": stop_on_entry},
    })
    session.handle_request({
        "seq": 3, "type": "request", "command": "setBreakpoints",
        "arguments": {"source": {"path": str(program_path)}, "breakpoints": [{"line": AR_LINE}]},
    })
    return session, writer, program_path


def register_value(writer, name):
    variables_response = writer.last_response()
    for v in variables_response["body"]["variables"]:
        if v["name"] == name:
            return v["value"]
    raise AssertionError(f"{name} not found in {variables_response}")


def test_initialize_sends_capabilities_and_initialized_event(tmp_path):
    session, writer, _ = make_session(tmp_path)
    init_response = writer.messages[0]
    assert init_response["success"] is True
    assert init_response["body"]["supportsConfigurationDoneRequest"] is True
    assert writer.events("initialized")


def test_setBreakpoints_verifies_exact_line(tmp_path):
    session, writer, _ = make_session(tmp_path)
    resp = writer.last_response()
    assert resp["body"]["breakpoints"] == [{"verified": True, "line": AR_LINE}]


def test_setBreakpoints_snaps_to_next_executable_line(tmp_path):
    program_path = tmp_path / "sum.hlasm"
    program_path.write_text(SUM_PROGRAM)
    writer = FakeWriter()
    session = DebugSession(reader=None, writer=writer)
    session.handle_request({"seq": 1, "type": "request", "command": "initialize", "arguments": {}})
    session.handle_request({
        "seq": 2, "type": "request", "command": "launch",
        "arguments": {"program": str(program_path), "stopOnEntry": False},
    })
    # line 1 (CSECT) has no instruction semantics; the next real instruction is line 2 (LA).
    session.handle_request({
        "seq": 3, "type": "request", "command": "setBreakpoints",
        "arguments": {"source": {}, "breakpoints": [{"line": 1}]},
    })
    resp = writer.last_response()
    assert resp["body"]["breakpoints"] == [{"verified": True, "line": 2}]


def test_configurationDone_stops_at_entry_when_requested(tmp_path):
    session, writer, _ = make_session(tmp_path, stop_on_entry=True)
    writer.clear()
    session.handle_request({"seq": 4, "type": "request", "command": "configurationDone", "arguments": {}})
    assert writer.events("stopped")[0]["body"]["reason"] == "entry"
    assert session.interp.cpu.psw.instruction_address == 0


def test_continue_stops_at_breakpoint_inside_loop_each_iteration(tmp_path):
    session, writer, _ = make_session(tmp_path, stop_on_entry=False)

    def stop_registers():
        session.handle_request({"seq": 100, "type": "request", "command": "variables",
                                 "arguments": {"variablesReference": 1}})
        return register_value(writer, "R1"), register_value(writer, "R2")

    # configurationDone runs straight to the first breakpoint hit (R1=10 just loaded, R2 still 0).
    session.handle_request({"seq": 4, "type": "request", "command": "configurationDone", "arguments": {}})
    assert writer.events("stopped")[-1]["body"]["reason"] == "breakpoint"
    r1, r2 = stop_registers()
    assert r1.startswith("10 ")
    assert r2.startswith("0 ")

    expected = [(20, 10), (30, 30), (40, 60)]
    for expected_r1, expected_r2 in expected:
        session.handle_request({"seq": 101, "type": "request", "command": "continue", "arguments": {}})
        assert writer.events("stopped")[-1]["body"]["reason"] == "breakpoint"
        r1, r2 = stop_registers()
        assert r1.startswith(f"{expected_r1} ")
        assert r2.startswith(f"{expected_r2} ")

    # one more continue: AR(2+40=100)/LA/BCT(0, no branch)/ST/END -> program terminates.
    session.handle_request({"seq": 101, "type": "request", "command": "continue", "arguments": {}})
    assert writer.events("terminated")
    total_addr = session.interp.data_labels["TOTAL"]
    assert session.interp.memory.read_int(total_addr, 4) == 100


def test_next_single_steps_one_instruction(tmp_path):
    session, writer, _ = make_session(tmp_path, stop_on_entry=True)
    session.handle_request({"seq": 4, "type": "request", "command": "configurationDone", "arguments": {}})
    assert session.interp.cpu.psw.instruction_address == 0
    writer.clear()
    session.handle_request({"seq": 5, "type": "request", "command": "next", "arguments": {}})
    assert session.interp.cpu.psw.instruction_address == 1
    assert writer.events("stopped")[-1]["body"]["reason"] == "step"


def test_evaluate_register_and_data_label(tmp_path):
    session, writer, _ = make_session(tmp_path, stop_on_entry=False)
    session.handle_request({"seq": 4, "type": "request", "command": "configurationDone", "arguments": {}})
    writer.clear()
    session.handle_request({"seq": 5, "type": "request", "command": "evaluate",
                             "arguments": {"expression": "R1"}})
    assert writer.last_response()["body"]["result"].startswith("10 ")

    session.handle_request({"seq": 6, "type": "request", "command": "evaluate",
                             "arguments": {"expression": "COUNT"}})
    assert writer.last_response()["body"]["result"].startswith("4 ")


def test_disconnect_stops_the_session_loop(tmp_path):
    session, writer, _ = make_session(tmp_path)
    session.handle_request({"seq": 4, "type": "request", "command": "disconnect", "arguments": {}})
    assert session._alive is False


def test_unknown_command_fails_gracefully(tmp_path):
    session, writer, _ = make_session(tmp_path)
    session.handle_request({"seq": 99, "type": "request", "command": "notARealCommand", "arguments": {}})
    resp = writer.last_response()
    assert resp["success"] is False
