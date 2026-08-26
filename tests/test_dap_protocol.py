import io

from hlasm_emulator.dap.protocol import DAPReader, DAPWriter


def test_write_then_read_round_trip():
    buf = io.BytesIO()
    DAPWriter(buf).write_message({"seq": 1, "type": "request", "command": "initialize"})
    buf.seek(0)
    message = DAPReader(buf).read_message()
    assert message == {"seq": 1, "type": "request", "command": "initialize"}


def test_read_multiple_messages_from_one_stream():
    buf = io.BytesIO()
    writer = DAPWriter(buf)
    writer.write_message({"seq": 1, "type": "event", "event": "a"})
    writer.write_message({"seq": 2, "type": "event", "event": "b"})
    buf.seek(0)
    reader = DAPReader(buf)
    assert reader.read_message()["event"] == "a"
    assert reader.read_message()["event"] == "b"


def test_read_returns_none_at_eof():
    reader = DAPReader(io.BytesIO(b""))
    assert reader.read_message() is None


def test_message_survives_multibyte_utf8_content():
    buf = io.BytesIO()
    DAPWriter(buf).write_message({"seq": 1, "type": "event", "event": "output", "body": {"output": "合計100"}})
    buf.seek(0)
    message = DAPReader(buf).read_message()
    assert message["body"]["output"] == "合計100"
