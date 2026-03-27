import re
from unittest.mock import MagicMock, patch

from app.utils import utils_get_timestamp, utils_list_serial_ports


class TestListSerialPorts:
    def test_returns_device_names(self):
        mock_ports = [MagicMock(device="COM1"), MagicMock(device="COM3")]
        with patch("serial.tools.list_ports.comports", return_value=mock_ports):
            assert utils_list_serial_ports() == ["COM1", "COM3"]

    def test_returns_empty_list_when_no_ports(self):
        with patch("serial.tools.list_ports.comports", return_value=[]):
            assert utils_list_serial_ports() == []

    def test_return_type_is_list(self):
        with patch("serial.tools.list_ports.comports", return_value=[]):
            assert isinstance(utils_list_serial_ports(), list)

    def test_single_port(self):
        with patch(
            "serial.tools.list_ports.comports",
            return_value=[MagicMock(device="/dev/ttyUSB0")],
        ):
            assert utils_list_serial_ports() == ["/dev/ttyUSB0"]

    def test_only_device_attribute_extracted(self):
        """Only the .device string is returned, not the full port object."""
        mock_port = MagicMock(device="COM5", description="USB Serial", hwid="USB\\VID_1234")
        with patch("serial.tools.list_ports.comports", return_value=[mock_port]):
            result = utils_list_serial_ports()
        assert result == ["COM5"]
        assert all(isinstance(p, str) for p in result)


class TestGetTimestamp:
    def test_format_matches_pattern(self):
        ts = utils_get_timestamp()
        assert re.fullmatch(r"\[\d{2}:\d{2}:\d{2}\.\d{3}\] ", ts)

    def test_returns_string(self):
        assert isinstance(utils_get_timestamp(), str)

    def test_milliseconds_are_three_digits(self):
        ts = utils_get_timestamp()
        ms = re.search(r"\.(\d+)\]", ts).group(1)
        assert len(ms) == 3
