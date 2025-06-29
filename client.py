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

# --- Event Handlers ---

@sio.on('connect', namespace='/serial')
def on_connect():
    """Triggered upon successful connection to the namespace."""
    logging.info(f"Successfully connected to the server's /serial namespace! SID: {sio.sid}")

@sio.on('disconnect', namespace='/serial')
def on_disconnect():
    """Triggered when disconnected from the server."""
    logging.warning("Disconnected from the server.")

@sio.on('serial_data_recv', namespace='/serial')
def on_serial_data(data):
    """
    This is the core handler. It's triggered whenever the server
    forwards data from the serial port.
    """
    message = data.get('data', 'No data received')
    logging.info(f"DATA RECEIVED <-- {message}")

@sio.on('serial_error', namespace='/serial')
def on_serial_error(data):
    """Triggered when the server sends a serial-related error."""
    logging.error(f"Server reported a serial error: {data.get('message')}")

# --- Main Application Logic ---
if __name__ == "__main__":
    # --- Use argparse to parse command-line arguments ---
    parser = argparse.ArgumentParser(
        description="A receive-only Python client for the Web Serial Monitor."
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
        help="The serial port baud rate (default: 115200)"
    )
    args = parser.parse_args()

    port_to_monitor = args.port
    baudrate_to_use = args.baudrate

    try:
        logging.info(f"Attempting to connect to server at {SERVER_URL}...")
        
        # Construct the connection URL with query parameters
        connect_url = f"{SERVER_URL}?port={port_to_monitor}&baudrate={baudrate_to_use}"
        logging.info(f"Connection URL: {connect_url}")
        
        # Connect to the server and the specified namespace
        sio.connect(connect_url, namespaces=['/serial'])

        logging.info("Connection successful. Now listening for incoming data. Press Ctrl+C to exit.")
        
        # Use a loop to keep the main thread alive and responsive to Ctrl+C
        while sio.connected:
            time.sleep(1)
        
        logging.warning("Client is no longer connected. Exiting loop.")

    except socketio.exceptions.ConnectionError as e:
        logging.error(f"Connection failed: {e}")
    except KeyboardInterrupt:
        logging.info("Shutdown signal received (Ctrl+C).")
    finally:
        # Ensure disconnection on exit
        if sio.connected:
            logging.info("Disconnecting from the server...")
            sio.disconnect()
        logging.info("Client has been shut down.")
