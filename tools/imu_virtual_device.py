"""
IMU Virtual Device — simulates a HipNuc IMU sending HI91 binary frames over a serial port.

Protocol layout (HipNuc CH protocol):
  [0x5A][0xA5][length:u16le][crc16:u16le][payload: length bytes]

HI91 payload (76 bytes):
  ofs  0     : item_type (0x91)
  ofs  1-2   : padding
  ofs  3     : temperature  int8
  ofs  4-7   : pressure     float32
  ofs  8-11  : system_time  uint32  (ms)
  ofs 12-23  : acc[3]       float32 x3  (m/s²)
  ofs 24-35  : gyr[3]       float32 x3  (rad/s)
  ofs 36-47  : mag[3]       float32 x3  (uT)
  ofs 48-51  : roll         float32  (deg)
  ofs 52-55  : pitch        float32  (deg)
  ofs 56-59  : yaw          float32  (deg)
  ofs 60-75  : quat[4]      float32 x4  (w, x, y, z)

Usage:
    python imu_virtual_device.py COM16 --baudrate 115200 --rate 100
"""

import argparse
import logging
import math
import struct
import sys
import time

import serial

CHSYNC1 = 0x5A
CHSYNC2 = 0xA5
CH_HDR_SIZE = 6
FRAME_TAG_HI91 = 0x91
HI91_PAYLOAD_SIZE = 76

GRAVITY = 9.80665

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [IMU DEVICE] - %(levelname)s - %(message)s",
    stream=sys.stdout,
)


def crc16_update(crc, data):
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            temp = crc << 1
            if crc & 0x8000:
                temp ^= 0x1021
            crc = temp
    return crc & 0xFFFF


def euler_to_quat(roll_deg, pitch_deg, yaw_deg):
    """Convert Euler angles (degrees) to quaternion (w, x, y, z)."""
    r = math.radians(roll_deg) / 2
    p = math.radians(pitch_deg) / 2
    y = math.radians(yaw_deg) / 2
    cr, sr = math.cos(r), math.sin(r)
    cp, sp = math.cos(p), math.sin(p)
    cy, sy = math.cos(y), math.sin(y)
    w = cr * cp * cy + sr * sp * sy
    x = sr * cp * cy - cr * sp * sy
    y_ = cr * sp * cy + sr * cp * sy
    z = cr * cp * sy - sr * sp * cy
    return (w, x, y_, z)


def build_hi91_frame(t_ms, roll, pitch, yaw, acc, gyr, mag, temperature=25, pressure=101325.0):
    """Build a complete HipNuc HI91 binary frame."""
    quat = euler_to_quat(roll, pitch, yaw)

    payload = bytearray(HI91_PAYLOAD_SIZE)
    payload[0] = FRAME_TAG_HI91
    # payload[1:3] padding — left as zero
    struct.pack_into("<b",  payload,  3, temperature)
    struct.pack_into("<f",  payload,  4, pressure)
    struct.pack_into("<I",  payload,  8, t_ms & 0xFFFFFFFF)
    struct.pack_into("<3f", payload, 12, *acc)
    struct.pack_into("<3f", payload, 24, *gyr)
    struct.pack_into("<3f", payload, 36, *mag)
    struct.pack_into("<f",  payload, 48, roll)
    struct.pack_into("<f",  payload, 52, pitch)
    struct.pack_into("<f",  payload, 56, yaw)
    struct.pack_into("<4f", payload, 60, *quat)

    length = len(payload)  # 76
    header_no_crc = struct.pack("<BB H", CHSYNC1, CHSYNC2, length)
    crc = crc16_update(0, header_no_crc + bytes(payload))
    header = struct.pack("<BB H H", CHSYNC1, CHSYNC2, length, crc)
    return bytes(header) + bytes(payload)


def run_imu_device(port, baudrate, rate_hz):
    logging.info("Opening port %s @ %d baud, output rate %d Hz", port, baudrate, rate_hz)
    try:
        ser = serial.Serial(port, baudrate, timeout=1)
        logging.info("IMU virtual device started on %s. Press Ctrl+C to stop.", port)
    except serial.SerialException as e:
        logging.error("Could not open port %s: %s", port, e)
        return

    interval = 1.0 / rate_hz
    start_wall = time.perf_counter()
    frame_count = 0

    try:
        while True:
            loop_start = time.perf_counter()
            elapsed = loop_start - start_wall
            t_ms = int(elapsed * 1000)

            # --- Simulate smooth motion ---
            roll  = 10.0  * math.sin(2 * math.pi * 0.1 * elapsed)          # ±10°  @ 0.1 Hz
            pitch = 5.0   * math.sin(2 * math.pi * 0.07 * elapsed + 1.0)   # ±5°   @ 0.07 Hz
            yaw   = (elapsed * 18.0) % 360.0                                # 18°/s continuous spin

            # Gyroscope (rad/s) — derivatives of the Euler angles above
            gyr_x = math.radians(10.0  * 2 * math.pi * 0.1  * math.cos(2 * math.pi * 0.1 * elapsed))
            gyr_y = math.radians(5.0   * 2 * math.pi * 0.07 * math.cos(2 * math.pi * 0.07 * elapsed + 1.0))
            gyr_z = math.radians(18.0)

            # Accelerometer (m/s²) — gravity vector rotated into body frame
            r = math.radians(roll)
            p = math.radians(pitch)
            acc_x = -GRAVITY * math.sin(p)
            acc_y =  GRAVITY * math.sin(r) * math.cos(p)
            acc_z =  GRAVITY * math.cos(r) * math.cos(p)

            # Magnetometer (uT) — fixed Earth field rotated into body frame
            mag_x = 30.0 * math.cos(p)
            mag_y = 30.0 * math.sin(r) * math.sin(p)
            mag_z = -50.0 * math.cos(r)

            frame = build_hi91_frame(
                t_ms=t_ms,
                roll=roll, pitch=pitch, yaw=yaw,
                acc=(acc_x, acc_y, acc_z),
                gyr=(gyr_x, gyr_y, gyr_z),
                mag=(mag_x, mag_y, mag_z),
                temperature=25,
                pressure=101325.0,
            )
            ser.write(frame)
            frame_count += 1

            if frame_count % rate_hz == 0:
                logging.info(
                    "t=%6.1fs  roll=%7.2f°  pitch=%6.2f°  yaw=%7.2f°  "
                    "acc=(%.2f, %.2f, %.2f) m/s²",
                    elapsed, roll, pitch, yaw, acc_x, acc_y, acc_z,
                )

            # Drain any received bytes (commands from web UI)
            if ser.in_waiting:
                rx = ser.read(ser.in_waiting)
                logging.info("Received <- %r", rx)

            # Sleep for the remainder of the interval
            elapsed_this_loop = time.perf_counter() - loop_start
            sleep_time = interval - elapsed_this_loop
            if sleep_time > 0:
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        logging.info("Shutdown signal received, closing port.")
    except Exception as e:
        logging.error("Unexpected error: %s", e)
    finally:
        if ser.is_open:
            ser.close()
            logging.info("Port %s closed.", port)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Virtual IMU device — streams HipNuc HI91 binary frames over a serial port.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "port",
        type=str,
        help="Serial port to write to (e.g. COM16, /dev/ttyUSB0)",
    )
    parser.add_argument(
        "--baudrate",
        type=int,
        default=115200,
        help="Baud rate (default: 115200)",
    )
    parser.add_argument(
        "--rate",
        type=int,
        default=100,
        help="Output frame rate in Hz (default: 100)",
    )
    args = parser.parse_args()
    run_imu_device(args.port, args.baudrate, args.rate)
