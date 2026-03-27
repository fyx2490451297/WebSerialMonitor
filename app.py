import logging
import os
import secrets
from flask import Flask, render_template, jsonify

from extensions import socketio
from serial_handlers import SerialNamespace
from utils import utils_list_serial_ports

# --- Application Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(threadName)s - %(message)s')
SERIAL_MONITOR_PORT = 50002

def create_app():
    """Creates the Flask application using the factory pattern."""
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    
    # --- Initialize Extensions ---
    # Import the socketio instance from extensions.py and bind it to the app
    socketio.init_app(app)

    # --- Register SocketIO Namespaces ---
    # Import SerialNamespace from serial_handlers.py and register it
    socketio.on_namespace(SerialNamespace('/serial'))

    # --- Register Flask Routes ---
    @app.route('/')
    def index():
        """Renders the all-in-one serial monitor main page."""
        try:
            serial_ports = utils_list_serial_ports()
            serial_ports.sort()
        except Exception as e:
            logging.error(f"Error finding serial ports: {e}")
            serial_ports = []
        
        common_baudrates = [9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600]
        data_bits = [5, 6, 7, 8]
        parity_options = [('N', 'None'), ('E', 'Even'), ('O', 'Odd')]
        stop_bits = ['1', '1.5', '2']

        return render_template(
            'SerialMonitor.html',
            ports=serial_ports,
            baudrates=common_baudrates,
            data_bits=data_bits,
            parity_options=parity_options,
            stop_bits=stop_bits,
            async_mode=socketio.async_mode
        )

    @app.route('/api/list_ports')
    def api_list_ports():
        """A new API endpoint that returns a JSON list of serial ports."""
        try:
            serial_ports = utils_list_serial_ports()
            serial_ports.sort()
            return jsonify(success=True, ports=serial_ports)
        except Exception as e:
            logging.error(f"Error finding serial ports via API: {e}")
            return jsonify(success=False, message=str(e)), 500
    
    return app

# --- Application Entry Point ---
if __name__ == '__main__':
    app = create_app()
    # Using socketio.run() allows it to select the best server (e.g., eventlet)
    socketio.run(
        app, 
        host='0.0.0.0', 
        port=SERIAL_MONITOR_PORT
    )
