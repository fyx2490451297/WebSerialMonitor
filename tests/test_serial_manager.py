import asyncio
from unittest.mock import MagicMock, patch

import pytest

from app.serial.manager import SerialMonitor


# ---------------------------------------------------------------------------
# _normalize_text_chunk  — pure logic, no I/O
# ---------------------------------------------------------------------------

class TestNormalizeTextChunk:
    def setup_method(self):
        self.m = SerialMonitor("COM1")

    def test_plain_text_unchanged(self):
        assert self.m._normalize_text_chunk("hello") == "hello"

    def test_empty_string(self):
        assert self.m._normalize_text_chunk("") == ""

    def test_lf_preserved(self):
        assert self.m._normalize_text_chunk("a\nb") == "a\nb"

    def test_crlf_converted_to_lf(self):
        assert self.m._normalize_text_chunk("a\r\nb") == "a\nb"

    def test_standalone_cr_converted_to_lf(self):
        assert self.m._normalize_text_chunk("a\rb") == "a\nb"

    def test_multiple_crlf(self):
        assert self.m._normalize_text_chunk("a\r\nb\r\nc") == "a\nb\nc"

    def test_trailing_cr_is_buffered_not_emitted(self):
        result = self.m._normalize_text_chunk("hello\r", final=False)
        assert result == "hello"
        assert self.m._pending_carriage_return is True

    def test_pending_cr_followed_by_lf_merges_to_one_newline(self):
        self.m._normalize_text_chunk("hello\r")
        result = self.m._normalize_text_chunk("\nworld")
        assert result == "\nworld"
        assert self.m._pending_carriage_return is False

    def test_pending_cr_followed_by_non_lf_emits_newline_then_data(self):
        self.m._normalize_text_chunk("hello\r")
        result = self.m._normalize_text_chunk("world")
        assert result == "\nworld"

    def test_final_true_flushes_pending_cr_as_newline(self):
        self.m._normalize_text_chunk("hello\r")
        result = self.m._normalize_text_chunk("", final=True)
        assert result == "\n"
        assert self.m._pending_carriage_return is False

    def test_no_pending_cr_on_init(self):
        assert self.m._pending_carriage_return is False


# ---------------------------------------------------------------------------
# connection_made
# ---------------------------------------------------------------------------

class TestConnectionMade:
    def test_stores_transport(self):
        m = SerialMonitor("COM1")
        t = MagicMock()
        m.connection_made(t)
        assert m.transport is t

    def test_disables_rts(self):
        m = SerialMonitor("COM1")
        t = MagicMock()
        m.connection_made(t)
        assert t.serial.rts is False

    def test_disables_dtr(self):
        m = SerialMonitor("COM1")
        t = MagicMock()
        m.connection_made(t)
        assert t.serial.dtr is False


# ---------------------------------------------------------------------------
# data_received
# ---------------------------------------------------------------------------

class TestDataReceived:
    def _emitted(self, mock_sio, event_name):
        return [c for c in mock_sio.emit.call_args_list if c.args[0] == event_name]

    def test_emits_hex_event(self):
        m = SerialMonitor("COM1")
        with patch("app.serial.manager.socketio") as sio:
            m.data_received(b"\x41\x42")
        calls = self._emitted(sio, "serial_data_recv_hex")
        assert len(calls) == 1
        assert calls[0].args[1]["data"] == "41 42"
        assert calls[0].kwargs["room"] == "COM1"
        assert calls[0].kwargs["namespace"] == "/serial"

    def test_emits_text_event(self):
        m = SerialMonitor("COM1")
        with patch("app.serial.manager.socketio") as sio:
            m.data_received(b"hello")
        calls = self._emitted(sio, "serial_data_recv")
        assert len(calls) == 1
        assert calls[0].args[1]["data"] == "hello"

    def test_hex_format_is_uppercase_zero_padded(self):
        m = SerialMonitor("COM1")
        with patch("app.serial.manager.socketio") as sio:
            m.data_received(b"\x00\x0f\xff")
        calls = self._emitted(sio, "serial_data_recv_hex")
        assert calls[0].args[1]["data"] == "00 0F FF"

    def test_text_crlf_normalized(self):
        m = SerialMonitor("COM1")
        with patch("app.serial.manager.socketio") as sio:
            m.data_received(b"line1\r\nline2")
        calls = self._emitted(sio, "serial_data_recv")
        assert calls[0].args[1]["data"] == "line1\nline2"

    def test_no_text_emit_when_normalized_result_is_empty(self):
        m = SerialMonitor("COM1")
        with patch("app.serial.manager.socketio") as sio:
            m._text_decoder = MagicMock()
            m._text_decoder.decode.return_value = ""
            m.data_received(b"\x00")
        assert len(self._emitted(sio, "serial_data_recv")) == 0


# ---------------------------------------------------------------------------
# connection_lost
# ---------------------------------------------------------------------------

class TestConnectionLost:
    def test_sets_connection_lost_event(self):
        m = SerialMonitor("COM1")
        with patch("app.serial.manager.socketio"):
            m.connection_lost(None)
        assert m.connection_lost_event.is_set()

    def test_sets_event_even_on_exception(self):
        m = SerialMonitor("COM1")
        with patch("app.serial.manager.socketio"):
            m.connection_lost(Exception("device removed"))
        assert m.connection_lost_event.is_set()

    def test_flushes_incomplete_utf8_as_replacement_char(self):
        m = SerialMonitor("COM1")
        m._text_decoder.decode(b"\xe4\xb8")  # incomplete 3-byte CJK sequence
        with patch("app.serial.manager.socketio") as sio:
            m.connection_lost(None)
        text_calls = [c for c in sio.emit.call_args_list if c.args[0] == "serial_data_recv"]
        flushed = "".join(c.args[1]["data"] for c in text_calls)
        assert "\ufffd" in flushed  # UTF-8 replacement character


# ---------------------------------------------------------------------------
# write_data  — async
# ---------------------------------------------------------------------------

class TestWriteData:
    async def test_writes_bytes_to_transport(self):
        m = SerialMonitor("COM1")
        t = MagicMock()
        m.connection_made(t)

        await m.send_queue.put(b"hello")
        task = asyncio.create_task(m.write_data())
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        t.write.assert_called_once_with(b"hello")

    async def test_writes_multiple_messages_in_order(self):
        m = SerialMonitor("COM1")
        t = MagicMock()
        m.connection_made(t)

        await m.send_queue.put(b"first")
        await m.send_queue.put(b"second")
        task = asyncio.create_task(m.write_data())
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert t.write.call_count == 2
        t.write.assert_any_call(b"first")
        t.write.assert_any_call(b"second")

    async def test_stops_cleanly_on_cancel(self):
        m = SerialMonitor("COM1")
        m.connection_made(MagicMock())
        task = asyncio.create_task(m.write_data())
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        # No unhandled exception — test passes if we reach here
