import logging

from app import create_app
from app.extensions import socketio
from config import HOST, PORT

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(threadName)s - %(message)s')

if __name__ == '__main__':
    app = create_app()
    socketio.run(app, host=HOST, port=PORT)
