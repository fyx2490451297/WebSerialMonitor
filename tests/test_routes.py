from unittest.mock import patch


class TestIndexRoute:
    def test_returns_200(self, http_client):
        with patch("app.utils_list_serial_ports", return_value=[]):
            resp = http_client.get("/")
        assert resp.status_code == 200

    def test_response_contains_html(self, http_client):
        with patch("app.utils_list_serial_ports", return_value=[]):
            resp = http_client.get("/")
        assert b"html" in resp.data.lower()

    def test_port_names_rendered_in_page(self, http_client):
        with patch("app.utils_list_serial_ports", return_value=["COM3", "COM5"]):
            resp = http_client.get("/")
        assert b"COM3" in resp.data
        assert b"COM5" in resp.data

    def test_survives_port_listing_exception(self, http_client):
        """A crash in port detection should not return 500 — degrade gracefully."""
        with patch("app.utils_list_serial_ports", side_effect=Exception("OS error")):
            resp = http_client.get("/")
        assert resp.status_code == 200


class TestApiListPorts:
    def test_returns_200_on_success(self, http_client):
        with patch("app.utils_list_serial_ports", return_value=["COM1"]):
            resp = http_client.get("/api/list_ports")
        assert resp.status_code == 200

    def test_content_type_is_json(self, http_client):
        with patch("app.utils_list_serial_ports", return_value=[]):
            resp = http_client.get("/api/list_ports")
        assert "application/json" in resp.content_type

    def test_success_flag_true(self, http_client):
        with patch("app.utils_list_serial_ports", return_value=[]):
            resp = http_client.get("/api/list_ports")
        assert resp.get_json()["success"] is True

    def test_ports_are_sorted(self, http_client):
        with patch("app.utils_list_serial_ports", return_value=["COM3", "COM1", "COM2"]):
            resp = http_client.get("/api/list_ports")
        assert resp.get_json()["ports"] == ["COM1", "COM2", "COM3"]

    def test_empty_port_list(self, http_client):
        with patch("app.utils_list_serial_ports", return_value=[]):
            resp = http_client.get("/api/list_ports")
        assert resp.get_json()["ports"] == []

    def test_error_returns_500(self, http_client):
        with patch("app.utils_list_serial_ports", side_effect=Exception("fail")):
            resp = http_client.get("/api/list_ports")
        assert resp.status_code == 500

    def test_error_response_has_success_false(self, http_client):
        with patch("app.utils_list_serial_ports", side_effect=Exception("fail")):
            resp = http_client.get("/api/list_ports")
        data = resp.get_json()
        assert data["success"] is False
        assert "message" in data
