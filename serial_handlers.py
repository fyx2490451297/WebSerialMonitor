import logging
import queue
from threading import Lock
from flask import request
from flask_socketio import Namespace

from extensions import socketio, connected_serials
from serial_manager import start_serial_monitor

class SerialNamespace(Namespace):
    """Handles all Socket.IO events related to serial communication."""
    def on_connect(self, auth=None):
        port = request.args.get('port')
        try:
            baudrate = int(request.args.get('baudrate', 115200))
        except (ValueError, TypeError):
            baudrate = 115200
            logging.warning(f"Client {request.sid} provided an invalid baud rate, using default {baudrate}")

        try:
            bytesize = int(request.args.get('bytesize', 8))
        except (ValueError, TypeError):
            bytesize = 8

        parity = request.args.get('parity', 'N')
        if parity not in ('N', 'E', 'O', 'M', 'S'):
            parity = 'N'

        stopbits_str = request.args.get('stopbits', '1')
        stopbits_map = {'1': 1, '1.5': 1.5, '2': 2}
        stopbits = stopbits_map.get(stopbits_str, 1)

        if not port:
            logging.warning(f"Client {request.sid} connected without a port, connection rejected.")
            return False

        self.enter_room(sid=request.sid,room=port)
        logging.info(f"Client {request.sid} has connected and joined room '{port}'")

        if port not in connected_serials:
            connected_serials[port] = {
                'baudrate': baudrate,
                'bytesize': bytesize,
                'parity': parity,
                'stopbits': stopbits,
                'serial_thread': None,
                'serial_thread_lock': Lock(),
                'clients': 1,
                'send_data': queue.Queue()
            }
        else:
            connected_serials[port]['clients'] += 1

        clients_num = connected_serials[port]['clients']
        logging.info(f"Number of clients for port {port}: {clients_num}")

        if connected_serials[port]['serial_thread'] is None:
            with connected_serials[port]['serial_thread_lock']:
                if connected_serials[port]['serial_thread'] is None:
                    logging.info(f"Starting serial monitor background task for port {port}.")
                    connected_serials[port]['serial_thread'] = socketio.start_background_task(
                        start_serial_monitor, port, baudrate, bytesize, parity, stopbits
                    )
        return True

    def on_disconnect(self):
        sid = request.sid
        disconnected_port = next((room for room in self.rooms(sid) if room != sid), None)
        
        if disconnected_port and disconnected_port in connected_serials:
            connected_serials[disconnected_port]['clients'] -= 1
            clients_num = connected_serials[disconnected_port]['clients']
            logging.info(f"Client {sid} has disconnected from room '{disconnected_port}'. Remaining clients: {clients_num}")

            if clients_num == 0:
                logging.info(f"All clients for port '{disconnected_port}' have disconnected. Preparing to stop monitor.")
                del connected_serials[disconnected_port]
        else:
            logging.warning(f"Client {sid} disconnected, but their port could not be determined or was already closed.")

    def on_serial_data_send(self, message):
        port = next((room for room in self.rooms(request.sid) if room != request.sid), None)

        if port and port in connected_serials:
            is_hex = message.get('is_hex', False)

            if is_hex:
                hex_str = message.get('data', '').replace(' ', '').replace(':', '')
                try:
                    data_bytes = bytes.fromhex(hex_str)
                    logging.info(f"SEND HEX -> {port}: {hex_str.upper()}")
                    connected_serials[port]['send_data'].put(data_bytes)
                except ValueError:
                    logging.warning(f"Invalid hex string from client {request.sid}: {hex_str}")
            else:
                send_data = message.get('data', '')
                end_with = message.get('end_with', '\r\n')
                send_data += end_with
                logging.info(f"SEND -> {port}: {send_data!r}")
                connected_serials[port]['send_data'].put(send_data.encode('utf-8', errors='ignore'))
