"""Wire framing for the Debug Adapter Protocol: each message is a JSON
object preceded by a ``Content-Length`` header, the same framing LSP
uses. This module only knows about bytes in/out -- message *content*
(requests/responses/events) is server.py's job.
"""
import json


class DAPReader:
    def __init__(self, stream):
        self._stream = stream

    def read_message(self):
        """Read one message, or return None at EOF."""
        headers = {}
        while True:
            line = self._stream.readline()
            if not line:
                return None  # EOF before a full header
            line = line.decode("ascii", errors="replace")
            if line in ("\r\n", "\n"):
                break
            if ":" in line:
                key, _, value = line.partition(":")
                headers[key.strip().lower()] = value.strip()

        length = int(headers.get("content-length", "0"))
        if length <= 0:
            return None
        body = self._stream.read(length)
        if body is None or len(body) < length:
            return None
        return json.loads(body.decode("utf-8"))


class DAPWriter:
    def __init__(self, stream):
        self._stream = stream

    def write_message(self, message: dict) -> None:
        data = json.dumps(message).encode("utf-8")
        header = f"Content-Length: {len(data)}\r\n\r\n".encode("ascii")
        self._stream.write(header)
        self._stream.write(data)
        self._stream.flush()
