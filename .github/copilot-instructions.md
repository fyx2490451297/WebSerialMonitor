# Copilot Instructions for WebSerialMonitor

## What This Project Does
A web-based serial port monitor that lets multiple remote users share and interact with a physical serial port in real time. The browser UI connects via WebSocket (Socket.IO); the backend bridges to the physical port using `pyserial-asyncio`.

## Running the App

```bash
# Install dependencies
pip install -r requirements.txt

# Start the server (listens on 0.0.0.0:50002)
python app.py

# Simulate a serial device (useful for testing without hardware)
python virtual_device.py COM16 --baudrate 115200

# Connect a headless Python client
python client.py COM17 --baudrate 115200
```

There are no tests or linters configured in this project.

## Architecture

```
app.py               Flask factory + HTTP routes (/ and /api/list_ports)
extensions.py        Shared singletons: socketio instance + connected_serials dict
serial_handlers.py   Socket.IO namespace (/serial) — handles connect/disconnect/send events
serial_manager.py    asyncio Protocol — owns the actual serial port I/O in a background thread
utils.py             Stateless helpers: port listing, timestamp formatting
virtual_device.py    Standalone test utility that emulates a serial device
client.py            Standalone Python Socket.IO client (reference/automation)
templates/           Single Jinja2 template: SerialMonitor.html
static/css/          style.css — CSS variables + Flexbox layout
static/js/           monitor.js — all frontend logic, no frameworks
```

### Data Flow

**Receive (device → browser):**
```
serial port → SerialMonitor.data_received() → socketio.emit('serial_data_recv', room=port) → browser
```

**Send (browser → device):**
```
browser → socket.emit('serial_data_send') → on_serial_data_send() → connected_serials[port]['send_data'].put() → main_serial_loop() reads queue → transport.write()
```

### Global State: `connected_serials`
Defined in `extensions.py`. Keyed by port name; each entry holds:
```python
{
  'baudrate': int,
  'serial_thread': Thread | None,
  'serial_thread_lock': threading.Lock(),
  'clients': int,          # reference count of connected browser tabs
  'send_data': queue.Queue()
}
```
The serial background thread starts when the first client connects to a port and stops when the last client disconnects. Thread-safe initialization uses double-checked locking.

### Async Model
`serial_manager.py` runs an `asyncio` event loop inside a plain `threading.Thread`. Flask-SocketIO uses `async_mode='threading'`. Do not introduce `eventlet`/`gevent` monkey-patching — it conflicts with this setup.

## Key Conventions

### Backend (Python)
- **Modules**: `snake_case`; **Classes**: `PascalCase`; **Constants**: `UPPER_SNAKE_CASE`
- Utility functions in `utils.py` are prefixed with `utils_` (e.g., `utils_list_serial_ports`)
- Logging uses the root logger (`logging.basicConfig`) at INFO/WARNING/ERROR — no per-module `getLogger` instances
- Serial data is decoded as UTF-8 with `errors='replace'`; line endings are normalised to `\n` in `data_received()`
- New Socket.IO events belong in `serial_handlers.py`; new serial I/O logic belongs in `serial_manager.py`
- `connected_serials[port]['send_data']` holds **bytes** (not strings); callers must encode before putting into the queue
- Serial port parameters (bytesize, parity, stopbits) are passed as Socket.IO query params on connect and forwarded to `pyserial_asyncio.create_serial_connection`

### Frontend (JavaScript / CSS)
- Vanilla JS only — no frameworks or build tools
- All frontend logic lives in `static/js/monitor.js`, scoped inside `DOMContentLoaded`
- CSS custom properties are defined in `:root` in `style.css` — use them for any new colours/spacing
- Log line types are colour-coded via classes: `.log-line-tx` (blue), `.log-line-rx` (dark), `.log-line-info` (grey italic)
- `MAX_LOG_LINES = 5000` caps the in-DOM log to prevent memory growth

### Socket.IO
- All events use the `/serial` namespace
- Clients join a **room named after the port string** (e.g. `"COM3"`); broadcasts target the room, never individual sids
- The client passes `port` and `baudrate` as Socket.IO query parameters on connect, not as event payloads
