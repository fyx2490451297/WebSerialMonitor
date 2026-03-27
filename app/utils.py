import serial.tools.list_ports
from datetime import datetime

def utils_list_serial_ports():
    """Returns a list of all available serial port device names."""
    ports = serial.tools.list_ports.comports()
    return [port.device for port in ports]

# This function is no longer used by the backend but can be kept for other purposes.
def utils_get_timestamp():
    """Returns a formatted timestamp string, e.g., [14:30:05.123]"""
    now = datetime.now()
    return now.strftime("[%H:%M:%S.") + f"{now.microsecond // 1000:03d}] "
