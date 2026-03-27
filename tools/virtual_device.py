import serial
import time
import random
import argparse
import logging
import sys

# --- Configure Logging ---
# Configure logging to output to standard output
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [VIRTUAL DEVICE] - %(levelname)s - %(message)s',
    stream=sys.stdout
)

def run_virtual_device(port, baudrate):
    """
    Simulates a serial port device.
    - Periodically sends simulated sensor data.
    - Listens for and prints any data received from the serial port (e.g., commands from the Web UI).
    """
    logging.info(f"Attempting to open virtual device on port: {port}, baud rate: {baudrate}")
    try:
        # Set a short timeout so the loop doesn't block forever on readline()
        ser = serial.Serial(port, baudrate, timeout=1)
        logging.info(f"Virtual device started successfully on {port}. Press Ctrl+C to stop.")
    except serial.SerialException as e:
        logging.error(f"Could not open port {port}: {e}")
        logging.error("Please ensure the port name is correct and you have permission to access it.")
        logging.error("On Windows, check the Device Manager. On Linux, you may need to use 'sudo' or add your user to the 'dialout' group.")
        return

    counter = 0
    try:
        while True:
            # --- 1. Send simulated data ---
            # Simulate a simple sensor, generating random temperature data
            temp = 20 + random.uniform(-2, 2)
            humidity = 50 + random.uniform(-5, 5)
            # The simulated device sends data ending with a newline character (\n), 
            # which our server-side logic relies on for processing.
            message_to_send = f"ID:{counter}, Temp:{temp:.2f}C, Humidity:{humidity:.2f}%\n".encode('utf-8')
            
            ser.write(message_to_send)
            logging.info(f"Sent -> {message_to_send.decode().strip()}")
            counter += 1

            # --- 2. Check for received data ---
            # Check if there is data in the input buffer
            if ser.in_waiting > 0:
                # Read one line of data (until a newline character)
                received_data = ser.readline().decode('utf-8').strip()
                if received_data:
                    logging.info(f"Received <- '{received_data}' (from Web UI!)")

            # Repeat every 3 seconds
            time.sleep(3)

    except KeyboardInterrupt:
        logging.info("Shutdown signal received (Ctrl+C), closing virtual device.")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
    finally:
        # Ensure the serial port is closed on exit
        if 'ser' in locals() and ser.is_open:
            ser.close()
            logging.info(f"Port {port} has been closed.")


if __name__ == "__main__":
    # --- Use argparse to parse command-line arguments ---
    parser = argparse.ArgumentParser(
        description="A virtual serial device simulator for testing the Web Serial Monitor.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        'port', 
        type=str, 
        help="The name of the serial port to use (e.g., COM16, /dev/ttyUSB0, /dev/pts/3)"
    )
    parser.add_argument(
        '--baudrate', 
        type=int, 
        default=115200, 
        help="The serial port baud rate (default: 115200)"
    )
    args = parser.parse_args()
    
    run_virtual_device(args.port, args.baudrate)
