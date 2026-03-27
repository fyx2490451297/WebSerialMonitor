import pytest

from app import create_app
from app.extensions import connected_serials


@pytest.fixture(scope="session")
def app():
    """Single Flask app instance shared across the whole test session."""
    _app = create_app()
    _app.config["TESTING"] = True
    return _app


@pytest.fixture
def http_client(app):
    """A fresh Flask test client per test function."""
    with app.test_client() as client:
        yield client


@pytest.fixture(autouse=True)
def reset_serial_state():
    """Wipe connected_serials before every test to prevent state leakage."""
    connected_serials.clear()
    yield
    connected_serials.clear()
