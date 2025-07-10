import asyncio
import serial
import serial_asyncio
import logging

from extensions import socketio, connected_serials

class SerialMonitor(asyncio.Protocol):
    """Asynchronous serial monitor protocol class."""
    def __init__(self, port, baudrate=115200):
        super().__init__()
        self.port = port
        self.transport = None
        self.send_queue = asyncio.Queue()
        self._buffer = bytearray()

    def connection_made(self, transport):
        self.transport = transport
        self.transport.serial.rts = False
        self.transport.serial.dtr = False
        logging.info(f"Successfully opened serial port: {self.port}")

    def data_received(self, data):
        self._buffer.extend(data)

        # Normalize line endings to \n
        self._buffer = self._buffer.replace(b'\r\n', b'\n')
        self._buffer = self._buffer.replace(b'\r', b'\n')

        while b'\n' in self._buffer:
            line_bytes, self._buffer = self._buffer.split(b'\n', 1)

            try:
                decoded_line = line_bytes.decode('utf-8', errors='replace')
                if decoded_line:
                    # Timestamps are no longer added here; this is handled by the frontend.
                    socketio.emit('serial_data_recv', {'data': decoded_line}, room=self.port, namespace='/serial')
            except Exception as e:
                logging.error(f"Error processing data from {self.port}: {e}")

    def connection_lost(self, exc):
        logging.warning(f"Connection to serial port {self.port} lost. Reason: {exc}")
        if self.transport and self.transport.loop.is_running():
            self.transport.loop.stop()

    async def write_data(self):
        while True:
            try:
                message_bytes = await self.send_queue.get()
                self.transport.write(message_bytes)
                self.send_queue.task_done()
            except asyncio.CancelledError:
                break

async def main_serial_loop(port, baudrate):
    """The main function for the asynchronous task."""
    try:
        loop = asyncio.get_running_loop()
        protocol = SerialMonitor(port, baudrate)
        transport, _ = await serial_asyncio.create_serial_connection(
            loop, lambda: protocol, port, baudrate
        )
        write_task = asyncio.create_task(protocol.write_data())
        while port in connected_serials:
            if not connected_serials[port]['send_data'].empty():
                data_to_send = connected_serials[port]['send_data'].get()
                await protocol.send_queue.put(data_to_send.encode('utf-8', errors='ignore'))
            await asyncio.sleep(0.05)
        
        logging.info(f"Shutting down tasks for port {port}...")
        write_task.cancel()
        if transport:
            transport.close()
    except (serial.SerialException, FileNotFoundError) as e:
        logging.error(f"Failed to connect to serial port {port}: {e}")
        socketio.emit('serial_error', {'port': port, 'message': str(e)}, room=port, namespace='/serial')
    except Exception as e:
        logging.error(f"An unexpected error occurred in the serial monitor for {port}: {e}")
        socketio.emit('serial_error', {'port': port, 'message': 'An unexpected error occurred.'}, room=port, namespace='/serial')
    finally:
        logging.info(f"Background task for '{port}' has shut down completely.")
        if port in connected_serials:
            del connected_serials[port]

def start_serial_monitor(port, baudrate):
    """The entry point for the background thread."""
    logging.info(f"Creating new asyncio event loop for port {port}.")
    try:
        asyncio.run(main_serial_loop(port, baudrate))
    except Exception as e:
        logging.error(f"Unhandled exception caught in start_serial_monitor for {port}: {e}")
