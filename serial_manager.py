import asyncio
import codecs
import queue
import serial
import serial_asyncio
import logging

from extensions import socketio, connected_serials, connected_serials_lock

class SerialMonitor(asyncio.Protocol):
    """Asynchronous serial monitor protocol class."""
    def __init__(self, port, baudrate=115200, bytesize=8, parity='N', stopbits=1):
        super().__init__()
        self.port = port
        self.transport = None
        self.send_queue = asyncio.Queue()
        self.connection_lost_event = asyncio.Event()
        self._text_decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        self._pending_carriage_return = False

    def connection_made(self, transport):
        self.transport = transport
        self.transport.serial.rts = False
        self.transport.serial.dtr = False
        logging.info(f"Successfully opened serial port: {self.port}")

    def data_received(self, data):
        # Emit raw hex bytes for clients in HEX display mode
        hex_str = ' '.join(f'{b:02X}' for b in data)
        socketio.emit('serial_data_recv_hex', {'data': hex_str}, room=self.port, namespace='/serial')

        try:
            decoded_chunk = self._text_decoder.decode(data)
            normalized_chunk = self._normalize_text_chunk(decoded_chunk)
            if normalized_chunk:
                socketio.emit('serial_data_recv', {'data': normalized_chunk}, room=self.port, namespace='/serial')
        except Exception as e:
            logging.error(f"Error processing data from {self.port}: {e}")

    def connection_lost(self, exc):
        try:
            flushed_text = self._text_decoder.decode(b'', final=True)
            normalized_chunk = self._normalize_text_chunk(flushed_text, final=True)
            if normalized_chunk:
                socketio.emit('serial_data_recv', {'data': normalized_chunk}, room=self.port, namespace='/serial')
        except Exception as e:
            logging.error(f"Error flushing buffered data from {self.port}: {e}")

        if exc:
            logging.warning(f"Connection to serial port {self.port} lost. Reason: {exc}")
        else:
            logging.info(f"Connection to serial port {self.port} closed.")

        self.connection_lost_event.set()

    async def write_data(self):
        while True:
            try:
                message_bytes = await self.send_queue.get()
                self.transport.write(message_bytes)
                self.send_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Error writing data to {self.port}: {e}")
                self.connection_lost_event.set()
                raise

    def _normalize_text_chunk(self, text_chunk, final=False):
        if self._pending_carriage_return:
            if text_chunk.startswith('\n'):
                text_chunk = text_chunk[1:]
            text_chunk = '\n' + text_chunk
            self._pending_carriage_return = False

        if text_chunk.endswith('\r') and not final:
            text_chunk = text_chunk[:-1]
            self._pending_carriage_return = True

        return text_chunk.replace('\r\n', '\n').replace('\r', '\n')

async def main_serial_loop(port, baudrate, bytesize=8, parity='N', stopbits=1):
    """The main function for the asynchronous task."""
    transport = None
    write_task = None
    try:
        loop = asyncio.get_running_loop()
        protocol = SerialMonitor(port, baudrate, bytesize, parity, stopbits)
        transport, _ = await serial_asyncio.create_serial_connection(
            loop, lambda: protocol, port, baudrate,
            bytesize=bytesize, parity=parity, stopbits=stopbits
        )
        with connected_serials_lock:
            port_state = connected_serials.get(port)
            if port_state is not None:
                port_state['status'] = 'open'
                port_state['error'] = None
                port_state['startup_event'].set()
        write_task = asyncio.create_task(protocol.write_data())

        while True:
            with connected_serials_lock:
                port_state = connected_serials.get(port)
                if port_state is None or port_state['clients'] <= 0:
                    break
                send_queue = port_state['send_data']

            if protocol.connection_lost_event.is_set():
                socketio.emit(
                    'serial_error',
                    {'port': port, 'message': f'Serial connection on {port} was lost.', 'fatal': True},
                    room=port,
                    namespace='/serial'
                )
                break

            try:
                data_bytes = send_queue.get_nowait()
                await protocol.send_queue.put(data_bytes)
                continue
            except queue.Empty:
                await asyncio.sleep(0.05)
        
        logging.info(f"Shutting down tasks for port {port}...")
    except (serial.SerialException, FileNotFoundError) as e:
        logging.error(f"Failed to connect to serial port {port}: {e}")
        with connected_serials_lock:
            port_state = connected_serials.get(port)
            if port_state is not None:
                port_state['status'] = 'error'
                port_state['error'] = str(e)
                port_state['startup_event'].set()
        socketio.emit('serial_error', {'port': port, 'message': str(e), 'fatal': True}, room=port, namespace='/serial')
    except Exception as e:
        logging.error(f"An unexpected error occurred in the serial monitor for {port}: {e}")
        with connected_serials_lock:
            port_state = connected_serials.get(port)
            if port_state is not None:
                port_state['status'] = 'error'
                port_state['error'] = 'An unexpected error occurred.'
                port_state['startup_event'].set()
        socketio.emit('serial_error', {'port': port, 'message': 'An unexpected error occurred.', 'fatal': True}, room=port, namespace='/serial')
    finally:
        if write_task is not None:
            write_task.cancel()
            try:
                await write_task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

        if transport is not None:
            transport.close()

        logging.info(f"Background task for '{port}' has shut down completely.")
        with connected_serials_lock:
            port_state = connected_serials.get(port)
            if port_state is not None:
                port_state['serial_thread'] = None
                port_state['startup_event'].set()
                connected_serials.pop(port, None)

def start_serial_monitor(port, baudrate, bytesize=8, parity='N', stopbits=1):
    """The entry point for the background thread."""
    logging.info(f"Creating new asyncio event loop for port {port}.")
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main_serial_loop(port, baudrate, bytesize, parity, stopbits))
    except Exception as e:
        logging.error(f"Unhandled exception caught in start_serial_monitor for {port}: {e}")
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        asyncio.set_event_loop(None)
        loop.close()
