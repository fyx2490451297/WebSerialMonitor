from config import HOST, PORT


def test_host_is_string():
    assert isinstance(HOST, str)


def test_host_default():
    assert HOST == "0.0.0.0"


def test_port_is_int():
    assert isinstance(PORT, int)


def test_port_default():
    assert PORT == 50002
