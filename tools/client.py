import socketio
import time
import logging
import argparse
import sys

# --- Configure Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [RX CLIENT] - %(levelname)s - %(message)s',
    stream=sys.stdout
)

# --- Server Configuration ---
SERVER_URL = "http://localhost:50002"

# Create a Socket.IO Client instance
sio = socketio.Client(reconnection_attempts=5, reconnection_delay=2)

# Set to True by --hex flag; handlers check this to decide what to print.
display_hex = False

# --- Event Handlers ---

@sio.on('connect', namespace='/serial')
def on_connect():
    """Triggered upon successful connection to the namespace."""
    mode = "HEX" if display_hex else "TEXT"
    logging.info(f"Connected to /serial namespace (display mode: {mode}). SID: {sio.sid}")

@sio.on('disconnect', namespace='/serial')
def on_disconnect():
    """Triggered when disconnected from the server."""
    logging.warning("Disconnected from the server.")

@sio.on('serial_data_recv', namespace='/serial')
def on_serial_data(data):
    """Text line from the serial port — printed only in TEXT mode."""
    if not display_hex:
        logging.info(f"RX TEXT <-- {data.get('data', '')}")

@sio.on('serial_data_recv_hex', namespace='/serial')
def on_serial_data_hex(data):
    """Raw hex dump of the same bytes — printed only in HEX mode."""
    if display_hex:
        logging.info(f"RX HEX  <-- {data.get('data', '')}")

@sio.on('serial_error', namespace='/serial')
def on_serial_error(data):
    """Triggered when the server sends a serial-related error."""
    port = data.get('port', '?')
    message = data.get('message', 'Unknown error')
    fatal = data.get('fatal', False)
    if fatal:
        logging.error(f"FATAL error on port {port}: {message} — disconnecting.")
        sio.disconnect()
    else:
        logging.warning(f"Serial error on port {port}: {message}")

# --- Main Application Logic ---
if __name__ == "__main__":
    # --- Use argparse to parse command-line arguments ---
    parser = argparse.ArgumentParser(
        description="A Python client for the Web Serial Monitor."
    )
    parser.add_argument(
        'port',
        type=str,
        help="The name of the serial port to monitor (e.g., COM17, /dev/pts/4)"
    )
    parser.add_argument(
        '--baudrate',
        type=int,
        default=115200,
        help="Baud rate (default: 115200)"
    )
    parser.add_argument(
        '--bytesize',
        type=int,
        default=8,
        choices=[5, 6, 7, 8],
        help="Data bits (default: 8)"
    )
    parser.add_argument(
        '--parity',
        type=str,
        default='N',
        choices=['N', 'E', 'O', 'M', 'S'],
        help="Parity: N/E/O/M/S (default: N)"
    )
    parser.add_argument(
        '--stopbits',
        type=str,
        default='1',
        choices=['1', '1.5', '2'],
        help="Stop bits (default: 1)"
    )
    parser.add_argument(
        '--server',
        type=str,
        default=SERVER_URL,
        help=f"Server URL (default: {SERVER_URL})"
    )
    parser.add_argument(
        '--hex',
        action='store_true',
        default=False,
        help="Display raw hex bytes instead of decoded text"
    )
    args = parser.parse_args()

    display_hex = args.hex

    query = (
        f"port={args.port}"
        f"&baudrate={args.baudrate}"
        f"&bytesize={args.bytesize}"
        f"&parity={args.parity}"
        f"&stopbits={args.stopbits}"
    )
    connect_url = f"{args.server}?{query}"

    try:
        logging.info(f"Connecting to {connect_url} ...")
        sio.connect(connect_url, namespaces=['/serial'])
        logging.info("Connected. Listening for data. Press Ctrl+C to exit.")

        while sio.connected:
            time.sleep(1)

        logging.warning("Client is no longer connected.")

    except socketio.exceptions.ConnectionError as e:
        # Server may refuse the connection (e.g. wrong config, port busy)
        logging.error(f"Connection refused: {e}")
    except KeyboardInterrupt:
        logging.info("Shutdown signal received (Ctrl+C).")
    finally:
        if sio.connected:
            logging.info("Disconnecting from the server...")
            sio.disconnect()
        logging.info("Client has been shut down.")
