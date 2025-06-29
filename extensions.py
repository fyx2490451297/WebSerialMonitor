from flask_socketio import SocketIO

# Instantiate SocketIO without binding it to an app.
# We will call init_app in app.py to complete the binding.
socketio = SocketIO(async_mode='threading')

# The global dictionary for tracking serial connections is also shared from here.
connected_serials = {}
