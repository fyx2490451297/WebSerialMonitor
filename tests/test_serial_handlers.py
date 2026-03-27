"""
Integration tests for the Socket.IO /serial namespace handlers.

Strategy
--------
socketio.start_background_task is patched with _fake_start_monitor, which
immediately sets status='open' and fires startup_event — simulating a
successful serial port open without touching real hardware.
"""
from unittest.mock import MagicMock, patch

import pytest

from app.extensions import connected_serials, connected_serials_lock, socketio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_start_monitor(func, port, *args):
    """Simulate the serial background thread completing initialisation."""
    with connected_serials_lock:
        state = connected_serials.get(port)
        if state:
            state["status"] = "open"
            state["startup_event"].set()
    return MagicMock()


def _connect(app, query_string, patch_start=True):
    """Helper: create a test client connected to /serial."""
    if patch_start:
        ctx = patch.object(socketio, "start_background_task", side_effect=_fake_start_monitor)
        ctx.__enter__()
    client = socketio.test_client(app, namespace="/serial", query_string=query_string)
    if patch_start:
        ctx.__exit__(None, None, None)
    return client


# ---------------------------------------------------------------------------
# on_connect
# ---------------------------------------------------------------------------

class TestOnConnect:
    def test_rejected_without_port_param(self, app):
        client = socketio.test_client(app, namespace="/serial")
        assert not client.is_connected("/serial")

    def test_accepted_with_valid_port(self, app):
        client = _connect(app, "port=COM1&baudrate=115200")
        assert client.is_connected("/serial")
        client.disconnect("/serial")

    def test_port_state_created_in_connected_serials(self, app):
        client = _connect(app, "port=COM1&baudrate=115200")
        assert "COM1" in connected_serials
        client.disconnect("/serial")

    def test_baudrate_stored_correctly(self, app):
        client = _connect(app, "port=COM1&baudrate=9600")
        assert connected_serials["COM1"]["baudrate"] == 9600
        client.disconnect("/serial")

    def test_client_count_is_one_after_first_connect(self, app):
        client = _connect(app, "port=COM1&baudrate=115200")
        assert connected_serials["COM1"]["clients"] == 1
        client.disconnect("/serial")

    def test_invalid_baudrate_falls_back_to_default(self, app):
        client = _connect(app, "port=COM2&baudrate=notanumber")
        assert connected_serials["COM2"]["baudrate"] == 115200
        client.disconnect("/serial")

    def test_invalid_bytesize_falls_back_to_default(self, app):
        client = _connect(app, "port=COM2&baudrate=115200&bytesize=9")
        assert connected_serials["COM2"]["bytesize"] == 8
        client.disconnect("/serial")

    def test_invalid_parity_falls_back_to_default(self, app):
        client = _connect(app, "port=COM2&baudrate=115200&parity=X")
        assert connected_serials["COM2"]["parity"] == "N"
        client.disconnect("/serial")

    def test_second_client_same_settings_accepted(self, app):
        c1 = _connect(app, "port=COM1&baudrate=115200")
        c2 = _connect(app, "port=COM1&baudrate=115200")
        assert c2.is_connected("/serial")
        assert connected_serials["COM1"]["clients"] == 2
        c1.disconnect("/serial")
        c2.disconnect("/serial")

    def test_second_client_different_baudrate_rejected(self, app):
        c1 = _connect(app, "port=COM1&baudrate=115200")
        c2 = _connect(app, "port=COM1&baudrate=9600")
        assert not c2.is_connected("/serial")
        assert connected_serials["COM1"]["clients"] == 1  # unchanged
        c1.disconnect("/serial")

    def test_timeout_causes_rejection(self, app):
        """startup_event.wait() returning False → connection refused."""
        with patch.object(socketio, "start_background_task", return_value=MagicMock()):
            with patch("app.serial.handlers.Event") as MockEvent:
                mock_ev = MagicMock()
                mock_ev.wait.return_value = False  # simulate 5-second timeout
                MockEvent.return_value = mock_ev
                client = socketio.test_client(
                    app, namespace="/serial", query_string="port=COM1&baudrate=115200"
                )
        assert not client.is_connected("/serial")

    def test_port_open_error_causes_rejection(self, app):
        """status='error' after startup_event fires → connection refused."""
        def _error_start(func, port, *args):
            with connected_serials_lock:
                state = connected_serials.get(port)
                if state:
                    state["status"] = "error"
                    state["error"] = "Port not found"
                    state["startup_event"].set()
            return MagicMock()

        with patch.object(socketio, "start_background_task", side_effect=_error_start):
            client = socketio.test_client(
                app, namespace="/serial", query_string="port=COM1&baudrate=115200"
            )
        assert not client.is_connected("/serial")


# ---------------------------------------------------------------------------
# on_disconnect
# ---------------------------------------------------------------------------

class TestOnDisconnect:
    def test_disconnect_decrements_client_count(self, app):
        c1 = _connect(app, "port=COM1&baudrate=115200")
        c2 = _connect(app, "port=COM1&baudrate=115200")
        assert connected_serials["COM1"]["clients"] == 2
        c1.disconnect("/serial")
        assert connected_serials["COM1"]["clients"] == 1
        c2.disconnect("/serial")

    def test_client_count_never_goes_negative(self, app):
        client = _connect(app, "port=COM1&baudrate=115200")
        client.disconnect("/serial")
        if "COM1" in connected_serials:
            assert connected_serials["COM1"]["clients"] >= 0


# ---------------------------------------------------------------------------
# on_serial_data_send
# ---------------------------------------------------------------------------

@pytest.fixture
def sio_client(app):
    """A connected /serial test client ready for send tests."""
    client = _connect(app, "port=COM1&baudrate=115200")
    yield client
    if client.is_connected("/serial"):
        client.disconnect("/serial")


class TestOnSerialDataSend:
    def test_text_data_placed_in_send_queue(self, sio_client):
        sio_client.emit("serial_data_send", {"data": "hello", "end_with": "\n"}, namespace="/serial")
        q = connected_serials["COM1"]["send_data"]
        assert q.get_nowait() == b"hello\n"

    def test_default_line_ending_is_crlf(self, sio_client):
        sio_client.emit("serial_data_send", {"data": "test"}, namespace="/serial")
        q = connected_serials["COM1"]["send_data"]
        assert q.get_nowait() == b"test\r\n"

    def test_empty_end_with_sends_no_line_ending(self, sio_client):
        sio_client.emit("serial_data_send", {"data": "raw", "end_with": ""}, namespace="/serial")
        q = connected_serials["COM1"]["send_data"]
        assert q.get_nowait() == b"raw"

    def test_hex_string_decoded_to_bytes(self, sio_client):
        sio_client.emit("serial_data_send", {"data": "48656C6C6F", "is_hex": True}, namespace="/serial")
        q = connected_serials["COM1"]["send_data"]
        assert q.get_nowait() == b"Hello"

    def test_hex_with_spaces_parsed(self, sio_client):
        sio_client.emit("serial_data_send", {"data": "48 65 6C 6C 6F", "is_hex": True}, namespace="/serial")
        q = connected_serials["COM1"]["send_data"]
        assert q.get_nowait() == b"Hello"

    def test_hex_with_colons_parsed(self, sio_client):
        sio_client.emit("serial_data_send", {"data": "48:65:6C:6C:6F", "is_hex": True}, namespace="/serial")
        q = connected_serials["COM1"]["send_data"]
        assert q.get_nowait() == b"Hello"

    def test_invalid_hex_emits_non_fatal_error(self, sio_client):
        sio_client.emit("serial_data_send", {"data": "ZZ", "is_hex": True}, namespace="/serial")
        received = sio_client.get_received("/serial")
        errors = [e for e in received if e["name"] == "serial_error"]
        assert errors, "Expected a serial_error event"
        assert errors[0]["args"][0]["fatal"] is False

    def test_invalid_hex_does_not_enqueue_anything(self, sio_client):
        sio_client.emit("serial_data_send", {"data": "ZZ", "is_hex": True}, namespace="/serial")
        q = connected_serials["COM1"]["send_data"]
        assert q.empty()

    def test_queue_is_empty_before_any_send(self, sio_client):
        assert connected_serials["COM1"]["send_data"].empty()
