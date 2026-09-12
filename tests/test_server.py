import json
import threading
import http.client
import socket

import pytest

from helixengine.runtime import Runtime
from helixengine.server import make_server


def test_loopback_startup_does_not_resolve_hostname(tmp_path, monkeypatch):
    def no_dns(*args, **kwargs):
        raise AssertionError('Loopback startup must not consult DNS')
    monkeypatch.setattr(socket, 'getfqdn', no_dns)
    runtime = Runtime(tmp_path, price_fetcher=lambda: b'')
    httpd = make_server(runtime, 0)
    try:
        assert httpd.server_name == '127.0.0.1'
        assert httpd.server_port > 0
    finally:
        httpd.server_close()


@pytest.fixture
def server(tmp_path):
    runtime = Runtime(tmp_path, price_fetcher=lambda: b"")
    httpd = make_server(runtime, 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd, runtime
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(3)


def request(httpd, method, path, body=None, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=3)
    connection.request(method, path, body=body, headers=headers or {})
    response = connection.getresponse()
    payload = response.read()
    result = (response.status, response.getheaders(), payload)
    connection.close()
    return result


def test_state_shape_and_hostile_routes_are_bounded(server):
    httpd, _ = server
    status, headers, body = request(httpd, "GET", "/api/release-state", headers={"Host": f"127.0.0.1:{httpd.server_port}"})
    assert status == 200
    state = json.loads(body)
    assert state["schema"] == "helix.app.v1"
    assert state["settings"] == {"enabled": True, "revision": 0}
    assert state["csrf_token"]
    assert state["release"]["model_wide_parity"] is False
    assert not any(key.lower().startswith("access-control") for key, _ in headers)
    for path in ("/research", "/api/state", "/../../etc/passwd"):
        assert request(httpd, "GET", path, headers={"Host": f"127.0.0.1:{httpd.server_port}"})[0] == 404
    assert request(httpd, "GET", "/api/release-state", headers={"Host": "evil.example"})[0] == 403
    assert request(httpd, "GET", "/api/release-events", headers={"Host": "evil.example"})[0] == 403


def test_settings_requires_exact_origin_csrf_and_revision(server):
    httpd, runtime = server
    host = f"127.0.0.1:{httpd.server_port}"
    _, _, body = request(httpd, "GET", "/api/release-state", headers={"Host": host})
    state = json.loads(body)
    payload = json.dumps({"enabled": False, "revision": 0})
    common = {"Host": host, "Content-Type": "application/json", "Content-Length": str(len(payload)), "X-Helix-CSRF": state["csrf_token"]}
    assert request(httpd, "POST", "/api/settings", payload, {**common, "Origin": "https://evil.example"})[0] == 403
    assert runtime.settings() == {"enabled": True, "revision": 0}
    assert request(httpd, "POST", "/api/settings", payload, {**common, "Origin": f"http://{host}", "X-Helix-CSRF": "wrong"})[0] == 403
    assert request(httpd, "POST", "/api/settings", "{}", {**common, "Origin": f"http://{host}"})[0] == 400
    duplicate = '{"enabled":false,"enabled":true,"revision":0}'
    duplicate_headers = {**common, "Origin": f"http://{host}", "Content-Length": str(len(duplicate))}
    assert request(httpd, "POST", "/api/settings", duplicate, duplicate_headers)[0] == 400
    assert request(httpd, "POST", "/api/settings", payload, {**common, "Origin": f"http://{host}"})[0] == 200
    stale = json.dumps({"enabled": True, "revision": 0})
    stale_headers = {**common, "Origin": f"http://{host}", "Content-Length": str(len(stale))}
    assert request(httpd, "POST", "/api/settings", stale, stale_headers)[0] == 409
    assert runtime.settings() == {"enabled": False, "revision": 1}


def test_sse_emits_release_snapshot(server):
    httpd, _ = server
    connection = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=3)
    connection.request("GET", "/api/release-events", headers={"Host": f"127.0.0.1:{httpd.server_port}"})
    response = connection.getresponse()
    assert response.status == 200
    assert response.readline().startswith(b"data: {")
    assert response.readline() == b"\n"
    connection.close()
