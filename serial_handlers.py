import logging
import queue
from threading import Event
from flask import request
from flask_socketio import Namespace
from socketio.exceptions import ConnectionRefusedError

from extensions import socketio, connected_serials, connected_serials_lock
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
        if bytesize not in (5, 6, 7, 8):
            logging.warning(f"Client {request.sid} provided an invalid data bits value, using default 8")
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

        should_start_monitor = False
        startup_event = None

        with connected_serials_lock:
            port_state = connected_serials.get(port)

            if port_state is not None and port_state['clients'] <= 0:
                connected_serials.pop(port, None)
                port_state = None

            if port_state is None:
                port_state = {
                    'baudrate': baudrate,
                    'bytesize': bytesize,
                    'parity': parity,
                    'stopbits': stopbits,
                    'serial_thread': None,
                    'clients': 1,
                    'send_data': queue.Queue(),
                    'status': 'opening',
                    'error': None,
                    'startup_event': Event()
                }
                connected_serials[port] = port_state
                should_start_monitor = True
            else:
                active_config = (
                    port_state['baudrate'],
                    port_state['bytesize'],
                    port_state['parity'],
                    port_state['stopbits']
                )
                requested_config = (baudrate, bytesize, parity, stopbits)
                if active_config != requested_config:
                    logging.warning(
                        "Client %s requested %s for port %s, but active config is %s. Connection rejected.",
                        request.sid,
                        requested_config,
                        port,
                        active_config
                    )
                    raise ConnectionRefusedError(
                        f"Port {port} is already open with settings {active_config}."
                    )

                port_state['clients'] += 1

            startup_event = port_state['startup_event']
            clients_num = port_state['clients']

        logging.info(f"Number of clients for port {port}: {clients_num}")

        if should_start_monitor:
            logging.info(f"Starting serial monitor background task for port {port}.")
            monitor_thread = socketio.start_background_task(
                start_serial_monitor, port, baudrate, bytesize, parity, stopbits
            )
            with connected_serials_lock:
                port_state = connected_serials.get(port)
                if port_state is not None:
                    port_state['serial_thread'] = monitor_thread

        if not startup_event.wait(timeout=5):
            self._rollback_client_registration(port)
            logging.error(f"Timed out while opening serial port {port} for client {request.sid}")
            raise ConnectionRefusedError(f"Timed out while opening port {port}.")

        with connected_serials_lock:
            port_state = connected_serials.get(port)
            status = port_state['status'] if port_state is not None else 'closed'
            error_message = port_state['error'] if port_state is not None else f"Port {port} is no longer available."

        if status != 'open':
            self._rollback_client_registration(port)
            logging.error(f"Failed to open serial port {port} for client {request.sid}: {error_message}")
            raise ConnectionRefusedError(error_message or f"Failed to open port {port}.")

        self.enter_room(sid=request.sid, room=port)
        logging.info(f"Client {request.sid} has connected and joined room '{port}'")
        return True

    def on_disconnect(self):
        sid = request.sid
        disconnected_port = next((room for room in self.rooms(sid) if room != sid), None)
        
        if not disconnected_port:
            logging.warning(f"Client {sid} disconnected, but their port could not be determined or was already closed.")
            return

        with connected_serials_lock:
            port_state = connected_serials.get(disconnected_port)
            if port_state is None:
                logging.warning(f"Client {sid} disconnected, but port '{disconnected_port}' was already cleaned up.")
                return

            port_state['clients'] = max(0, port_state['clients'] - 1)
            clients_num = port_state['clients']

        logging.info(f"Client {sid} has disconnected from room '{disconnected_port}'. Remaining clients: {clients_num}")

        if clients_num == 0:
            logging.info(f"All clients for port '{disconnected_port}' have disconnected. Preparing to stop monitor.")

    def on_serial_data_send(self, message):
        message = message or {}
        port = next((room for room in self.rooms(request.sid) if room != request.sid), None)

        if not port:
            logging.warning(f"Client {request.sid} attempted to send data without an active port.")
            socketio.emit('serial_error', {'message': 'No active serial port is connected.'}, to=request.sid, namespace='/serial')
            return

        with connected_serials_lock:
            port_state = connected_serials.get(port)
            send_queue = port_state['send_data'] if port_state is not None else None

        if send_queue is None:
            logging.warning(f"Client {request.sid} attempted to send data to inactive port {port}.")
            socketio.emit('serial_error', {'message': f'Port {port} is no longer active.'}, to=request.sid, namespace='/serial')
            return

        is_hex = message.get('is_hex', False)

        if is_hex:
            hex_str = str(message.get('data', '') or '').replace(' ', '').replace(':', '')
            try:
                data_bytes = bytes.fromhex(hex_str)
                logging.info(f"SEND HEX -> {port}: {hex_str.upper()}")
                send_queue.put(data_bytes)
            except ValueError:
                logging.warning(f"Invalid hex string from client {request.sid}: {hex_str}")
                socketio.emit('serial_error', {'message': 'Invalid HEX payload.', 'fatal': False}, to=request.sid, namespace='/serial')
        else:
            send_data = str(message.get('data', '') or '')
            end_with = str(message.get('end_with', '\r\n') or '')
            send_data += end_with
            logging.info(f"SEND -> {port}: {send_data!r}")
            send_queue.put(send_data.encode('utf-8', errors='replace'))

    def _rollback_client_registration(self, port):
        with connected_serials_lock:
            port_state = connected_serials.get(port)
            if port_state is None:
                return

            port_state['clients'] = max(0, port_state['clients'] - 1)
            if port_state['clients'] == 0 and port_state['status'] != 'open':
                connected_serials.pop(port, None)
