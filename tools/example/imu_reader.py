import copy
import logging
import math
import struct
from collections import deque

import serial

# Constant definitions
CHSYNC1 = 0x5A
CHSYNC2 = 0xA5
CH_HDR_SIZE = 6

GRAVITY = 9.80665
R2D = 57.29577951308232


# Data item identifiers
FRAME_TAG_HI91 = 0x91
FRAME_TAG_HI81 = 0x81


class hipnuc_frame:
    def __init__(self):
        self.reset()

    def reset(self):
        self.temperature = None
        self.pressure = None
        self.system_time_ms = None
        self.acc = None
        self.gyr = None
        self.mag = None
        self.quat = None
        self.roll = None
        self.pitch = None
        self.yaw = None
        self.ins_status = None
        self.gpst_wn = None
        self.gpst_tow = None
        self.utc_year = None
        self.utc_month = None
        self.utc_day = None
        self.utc_hour = None
        self.utc_min = None
        self.utc_msec = None
        self.ins_lon = None
        self.ins_lat = None
        self.ins_msl = None
        self.pdop = None
        self.hdop = None
        self.solq_pos = None
        self.nv_pos = None
        self.solq_heading = None
        self.nv_heading = None
        self.diff_age = None
        self.undulation = None
        self.vel_enu = None
        self.acc_enu = None

    def to_dict(self):
        """Return a dictionary representation of non-null fields"""
        return {k: v for k, v in self.__dict__.items() if v is not None}

    def clone(self):
        """Return a deep copy of the frame to prevent downstream mutation."""
        cloned = hipnuc_frame()
        cloned.__dict__ = copy.deepcopy(self.__dict__)
        return cloned


class hipnuc_parser:
    def __init__(self):
        self.CHSYNC1 = CHSYNC1
        self.CHSYNC2 = CHSYNC2
        self.CH_HDR_SIZE = CH_HDR_SIZE
        self.buffer = bytearray()
        self.frame = hipnuc_frame()

    @staticmethod
    def crc16_update(crc, data):
        for byte in data:
            crc ^= byte << 8
            for _ in range(8):
                temp = crc << 1
                if crc & 0x8000:
                    temp ^= 0x1021
                crc = temp
        return crc & 0xFFFF

    def parse_item(self, item_type, data, ofs):
        try:
            if item_type == FRAME_TAG_HI91:
                self._parse_hi91(data, ofs)
                return ofs + 76
            elif item_type == FRAME_TAG_HI81:
                self._parse_hi81(data, ofs)
                return ofs + 104
            else:
                logging.warning(f"Unknown item type: {item_type}")
                return ofs + 1
        except struct.error as e:
            logging.error(f"Error parsing data: {e}")
            return ofs + 1

    def _parse_hi91(self, data, ofs):
        self.frame.temperature = struct.unpack_from("<b", data, ofs + 3)[0]
        self.frame.pressure = struct.unpack_from("<f", data, ofs + 4)[0]
        self.frame.system_time_ms = struct.unpack_from("<I", data, ofs + 8)[0]
        self.frame.acc = struct.unpack_from("<3f", data, ofs + 12)
        self.frame.gyr = struct.unpack_from("<3f", data, ofs + 24)
        self.frame.mag = struct.unpack_from("<3f", data, ofs + 36)
        self.frame.roll = struct.unpack_from("<f", data, ofs + 48)[0]
        self.frame.pitch = struct.unpack_from("<f", data, ofs + 52)[0]
        self.frame.yaw = struct.unpack_from("<f", data, ofs + 56)[0]
        self.frame.quat = struct.unpack_from("<4f", data, ofs + 60)

    def _parse_hi81(self, data, ofs):
        self.frame.ins_status = struct.unpack_from("<B", data, ofs + 3)[0]
        self.frame.gpst_wn = struct.unpack_from("<H", data, ofs + 4)[0]
        self.frame.gpst_tow = struct.unpack_from("<I", data, ofs + 6)[0] * 1e-3
        self.frame.gyr = [
            x * 0.001 * R2D for x in struct.unpack_from("<3h", data, ofs + 12)
        ]  # Convert to degrees per second
        self.frame.acc = [
            x * 0.0048828 / GRAVITY for x in struct.unpack_from("<3h", data, ofs + 18)
        ]  # Convert to G
        self.frame.mag = [
            x * 0.030517 for x in struct.unpack_from("<3h", data, ofs + 24)
        ]  # Convert to uT
        self.frame.pressure = struct.unpack_from("<h", data, ofs + 30)[0] + 100000

        self.frame.temperature = struct.unpack_from("<b", data, ofs + 34)[0]
        self.frame.utc_year = struct.unpack_from("<B", data, ofs + 35)[0]
        self.frame.utc_month = struct.unpack_from("<B", data, ofs + 36)[0]
        self.frame.utc_day = struct.unpack_from("<B", data, ofs + 37)[0]
        self.frame.utc_hour = struct.unpack_from("<B", data, ofs + 38)[0]
        self.frame.utc_min = struct.unpack_from("<B", data, ofs + 39)[0]
        self.frame.utc_msec = struct.unpack_from("<H", data, ofs + 40)[0]
        self.frame.roll = (
            struct.unpack_from("<h", data, ofs + 42)[0] * 0.01
        )  # Convert to degrees
        self.frame.pitch = (
            struct.unpack_from("<h", data, ofs + 44)[0] * 0.01
        )  # Convert to degrees
        self.frame.yaw = (
            struct.unpack_from("<H", data, ofs + 46)[0] * 0.01
        )  # Convert to degrees
        self.frame.quat = [
            x * 0.0001 for x in struct.unpack_from("<4h", data, ofs + 48)
        ]  # Convert to quaternion
        self.frame.ins_lon = (
            struct.unpack_from("<i", data, ofs + 56)[0] * 1e-7
        )  # Convert to degrees
        self.frame.ins_lat = (
            struct.unpack_from("<i", data, ofs + 60)[0] * 1e-7
        )  # Convert to degrees
        self.frame.ins_msl = (
            struct.unpack_from("<i", data, ofs + 64)[0] * 1e-3
        )  # Convert to meters
        self.frame.pdop = (
            struct.unpack_from("<B", data, ofs + 68)[0] * 0.1
        )  # Convert to unit
        self.frame.hdop = (
            struct.unpack_from("<B", data, ofs + 69)[0] * 0.1
        )  # Convert to unit
        self.frame.solq_pos = struct.unpack_from("<B", data, ofs + 70)[0]
        self.frame.nv_pos = struct.unpack_from("<B", data, ofs + 71)[0]
        self.frame.solq_heading = struct.unpack_from("<B", data, ofs + 72)[0]
        self.frame.nv_heading = struct.unpack_from("<B", data, ofs + 73)[0]
        self.frame.diff_age = struct.unpack_from("<B", data, ofs + 74)[0]
        self.frame.undulation = (
            struct.unpack_from("<h", data, ofs + 75)[0] * 0.01
        )  # Convert to meters
        self.frame.vel_enu = [
            x * 0.01 for x in struct.unpack_from("<3h", data, ofs + 78)
        ]  # Convert to meters per second
        self.frame.acc_enu = [
            x * 0.0048828 / GRAVITY for x in struct.unpack_from("<3h", data, ofs + 84)
        ]  # Convert to G
        self.frame.system_time_ms = struct.unpack_from("<I", data, ofs + 90)[0]

    def parse_data(self, data):
        """Parse data"""
        ofs = 0
        while ofs < len(data):
            item_type = data[ofs]
            ofs = self.parse_item(item_type, data, ofs)

    def parse(self, new_data):
        """Decode new data and return successfully parsed frames"""
        self.buffer += new_data
        frames = []
        while len(self.buffer) >= self.CH_HDR_SIZE:
            if self.buffer[0] == self.CHSYNC1 and self.buffer[1] == self.CHSYNC2:
                length = struct.unpack_from("<H", self.buffer, 2)[0]
                if len(self.buffer) >= self.CH_HDR_SIZE + length:
                    frame = self.buffer[: self.CH_HDR_SIZE + length]
                    crc_calculated = self.crc16_update(0, frame[:4] + frame[6:])
                    crc_received = struct.unpack_from("<H", frame, 4)[0]
                    if crc_calculated == crc_received:
                        self.frame.reset()  # Reset data
                        self.frame.frame_type = frame[6]  # 获取帧类型并保存到实例中
                        self.parse_data(frame[self.CH_HDR_SIZE :])
                        frames.append(self.frame.clone())  # Add parsed IMU data to list
                    else:
                        logging.error("CRC check failed")
                    del self.buffer[: self.CH_HDR_SIZE + length]
                else:
                    break
            else:
                del self.buffer[0]
        return frames

    @staticmethod
    def print_parsed_data(data):
        """Format and print IMU data in a professional and compact format"""
        if data.frame_type is not None:
            data_fields = [
                ("Frame Type", f"HI{data.frame_type:02X}"),
                (
                    "Temperature (C)",
                    f"{data.temperature:<6}" if data.temperature is not None else None,
                ),
                (
                    "Pressure (Pa)",
                    f"{data.pressure:<9.3f}" if data.pressure is not None else None,
                ),
                (
                    "System_time_ms",
                    (
                        f"{data.system_time_ms:<9}"
                        if data.system_time_ms is not None
                        else None
                    ),
                ),
                ("Roll (deg)", f"{data.roll:<9.3f}" if data.roll is not None else None),
                (
                    "Pitch (deg)",
                    f"{data.pitch:<9.3f}" if data.pitch is not None else None,
                ),
                ("Yaw (deg)", f"{data.yaw:<9.3f}" if data.yaw is not None else None),
                (
                    "INS Status",
                    f"{data.ins_status:<9}" if data.ins_status is not None else None,
                ),
                (
                    "GPS Week No.",
                    f"{data.gpst_wn:<9}" if data.gpst_wn is not None else None,
                ),
                (
                    "GPS TOW (s)",
                    f"{data.gpst_tow:<9} s" if data.gpst_tow is not None else None,
                ),
                (
                    "UTC Time",
                    (
                        f"20{data.utc_year:<2}-{data.utc_month:02}-{data.utc_day:02} {data.utc_hour:02}:{data.utc_min:02}:{data.utc_msec:06.3f}"
                        if all(
                            [
                                data.utc_year,
                                data.utc_month,
                                data.utc_day,
                                data.utc_hour,
                                data.utc_min,
                                data.utc_msec,
                            ]
                        )
                        else None
                    ),
                ),
                (
                    "INS Longitude (deg)",
                    f"{data.ins_lon:<12.7f}" if data.ins_lon is not None else None,
                ),
                (
                    "INS Latitude (deg)",
                    f"{data.ins_lat:<12.7f}" if data.ins_lat is not None else None,
                ),
                (
                    "INS MSL (m)",
                    f"{data.ins_msl:<9.3f}" if data.ins_msl is not None else None,
                ),
                ("PDOP", f"{data.pdop:<9.1f}" if data.pdop is not None else None),
                ("HDOP", f"{data.hdop:<9.1f}" if data.hdop is not None else None),
                (
                    "Position Quality",
                    f"{data.solq_pos:<9}" if data.solq_pos is not None else None,
                ),
                ("Sat No. ", f"{data.nv_pos:<9}" if data.nv_pos is not None else None),
                (
                    "Heading Quality",
                    (
                        f"{data.solq_heading:<9}"
                        if data.solq_heading is not None
                        else None
                    ),
                ),
                (
                    "NV Heading",
                    f"{data.nv_heading:<9}" if data.nv_heading is not None else None,
                ),
                (
                    "Diff Age",
                    f"{data.diff_age:<9}" if data.diff_age is not None else None,
                ),
                (
                    "Undulation",
                    f"{data.undulation:<9}" if data.undulation is not None else None,
                ),
                (
                    "Acceleration (G)",
                    (
                        f"({data.acc[0]:<9.3f}, {data.acc[1]:<9.3f}, {data.acc[2]:<9.3f})"
                        if data.acc is not None
                        else None
                    ),
                ),
                (
                    "Gyroscope (deg/s)",
                    (
                        f"({data.gyr[0]:<9.3f}, {data.gyr[1]:<9.3f}, {data.gyr[2]:<9.3f})"
                        if data.gyr is not None
                        else None
                    ),
                ),
                (
                    "Magnetometer (uT)",
                    (
                        f"({data.mag[0]:<9.3f}, {data.mag[1]:<9.3f}, {data.mag[2]:<9.3f})"
                        if data.mag is not None
                        else None
                    ),
                ),
                (
                    "Quaternion",
                    (
                        f"({data.quat[0]:<9.3f}, {data.quat[1]:<9.3f}, {data.quat[2]:<9.3f}, {data.quat[3]:<9.3f})"
                        if data.quat is not None
                        else None
                    ),
                ),
                (
                    "Velocity ENU (m/s)",
                    (
                        f"({data.vel_enu[0]:<9.3f}, {data.vel_enu[1]:<9.3f}, {data.vel_enu[2]:<9.3f})"
                        if data.vel_enu is not None
                        else None
                    ),
                ),
                (
                    "Acceleration ENU (m/s²)",
                    (
                        f"({data.acc_enu[0]:<9.3f}, {data.acc_enu[1]:<9.3f}, {data.acc_enu[2]:<9.3f})"
                        if data.acc_enu is not None
                        else None
                    ),
                ),
            ]

            # Print the data fields
            for label, value in data_fields:
                if value is not None:
                    print(f"{label:<24}: {value}")


class IMUReader:
    """High-level helper that reads HipNuc IMU data and exposes the latest frame."""

    DEFAULT_MIN_READ_SIZE = 200

    def __init__(
        self,
        port="/dev/ttyUSBimuC",
        baudrate=115200,
        timeout=1,
        min_read_size=None,
        logger=None,
    ):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.min_read_size = min_read_size or self.DEFAULT_MIN_READ_SIZE
        self.logger = logger or logging.getLogger(__name__)

        self._serial = None
        self._latest_frame = None
        self.parser = hipnuc_parser()

    def connect(self):
        """Ensure the serial connection is open."""
        if self._serial and self._serial.is_open:
            return self._serial
        try:
            self._serial = serial.Serial(
                self.port,
                self.baudrate,
                timeout=self.timeout,
            )
            self.logger.info(
                "Connected to IMU on %s @ %s baud", self.port, self.baudrate
            )
        except serial.SerialException as exc:
            self.logger.error("Failed to open IMU serial port: %s", exc)
            raise
        return self._serial

    def close(self):
        """Close the serial connection."""
        if self._serial and self._serial.is_open:
            self._serial.close()
            self.logger.info("Closed IMU serial connection")

    def read_raw(self):
        """Read currently available raw bytes from the IMU serial stream."""
        ser = self.connect()
        bytes_to_read = ser.in_waiting
        if bytes_to_read <= 0:
            return b""
        return ser.read(bytes_to_read)

    def read_new_frames(self):
        """Keep reading until at least one new frame is parsed or the read times out."""
        try:
            while True:
                data = self.read_raw()
                if not data:
                    return None

                frames = self.parser.parse(data)
                if frames:
                    self._latest_frame = frames[-1]
                    return frames
        except serial.SerialException as exc:
            self.logger.error("Serial read failed: %s", exc)
            return None

    def get_latest_frame(self, refresh=False):
        """
        Return the latest cached frame.

        Args:
            refresh: When True, refresh the cache before returning the latest frame.
        """
        if refresh:
            self.read_new_frames()
        if self._latest_frame is None:
            self.read_new_frames()
        return self._latest_frame

    def get_latest_frames(self, refresh=True):
        """
        Return newly parsed frames when refreshing, or the cached latest frame as a
        single-item list otherwise.

        Args:
            refresh: When True (default) read from the IMU before returning.
        """
        if refresh:
            return self.read_new_frames()
        latest_frame = self.get_latest_frame(refresh=False)
        return [latest_frame] if latest_frame else None

    def get_latest_data(self, refresh=True):
        """
        Return the latest IMU data as a dictionary.

        Args:
            refresh: When True (default) read from the IMU before returning.
        """
        if refresh:
            frames = self.read_new_frames()
            frame = frames[-1] if frames else None
        else:
            frame = self.get_latest_frame(refresh=False)
        return frame.to_dict() if frame else None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import time

    WRITE_TO_FILE = False
    PRINT_PARSED_DATA = False

    imu_csv = "imu0.csv"
    with IMUReader() as imu:
        recent_frame_times = deque()
        f = None
        if WRITE_TO_FILE:
            f = open(imu_csv, "w")
            f.write("timestamp,omega_x,omega_y,omega_z,alpha_x,alpha_y,alpha_z\n")

        count = int(3.5 * 60 * 60 * 100)  # 3.5 hours at 100Hz
        for _ in range(count):
            frames = imu.read_new_frames()
            if frames:
                for frame in frames:
                    omega_x = math.radians(frame.gyr[0])
                    omega_y = math.radians(frame.gyr[1])
                    omega_z = math.radians(frame.gyr[2])
                    alpha_x = frame.acc[0] * 9.80665
                    alpha_y = frame.acc[1] * 9.80665
                    alpha_z = frame.acc[2] * 9.80665

                    timestamp_ns = time.time_ns()
                    line = (
                        f"{timestamp_ns},{omega_x},{omega_y},{omega_z},"
                        f"{alpha_x},{alpha_y},{alpha_z}"
                    )
                    current_wall_time = time.perf_counter()
                    recent_frame_times.append(current_wall_time)
                    while (
                        recent_frame_times
                        and current_wall_time - recent_frame_times[0] > 1.0
                    ):
                        recent_frame_times.popleft()
                    fps = len(recent_frame_times)

                    if WRITE_TO_FILE:
                        f.write(f"{line}\n")
                    else:
                        if PRINT_PARSED_DATA:
                            hipnuc_parser.print_parsed_data(frame)
                        else:
                            if fps is not None:
                                print(f"{line},fps={fps:.3f}")
                            else:
                                print(line)
            else:
                logging.info("No IMU frame parsed from the device.")
            time.sleep(0.005)

        if f is not None:
            f.close()
