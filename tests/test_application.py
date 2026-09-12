"""Black-box application checks: command execution, switch, HTTP and evidence."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def test_http_switch_controls_new_runs_without_rerun(tmp_path, monkeypatch):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    origin = f'http://127.0.0.1:{port}'
    args = [sys.executable, '-m', 'helixengine', '--data-dir', str(tmp_path/'data')]
    server = subprocess.Popen([sys.executable, '-c',
        'import faulthandler; faulthandler.dump_traceback_later(10); from helixengine.cli import main; raise SystemExit(main())',
        *args[3:], 'serve', '--port', str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    def request(path='/api/release-state', data=None, token=None, claimed_origin=None):
        headers = {}
        if data is not None:
            headers = {'Content-Type': 'application/json', 'Origin': claimed_origin or origin,
                       'X-Helix-CSRF': token or ''}
        with urlopen(Request(origin+path, data=json.dumps(data).encode() if data is not None else None, headers=headers), timeout=3) as response:
            return response.status, json.loads(response.read())

    try:
        deadline = time.monotonic()+15
        while True:
            try:
                _, state = request()
                break
            except (URLError, ConnectionError):
                if server.poll() is not None or time.monotonic() > deadline:
                    server.terminate()
                    try:
                        _, diagnostic = server.communicate(timeout=5)
                    except subprocess.TimeoutExpired:
                        server.kill()
                        _, diagnostic = server.communicate(timeout=5)
                    raise AssertionError(f'Server did not start; exit={server.returncode}; stderr={diagnostic.decode(errors="replace")}')
                time.sleep(.1)
        for path in ['/research', '/api/state', '/../../pyproject.toml']:
            try:
                request(path)
                raise AssertionError(f'Unexpected exposed route: {path}')
            except HTTPError as exc:
                assert exc.code in (400, 403, 404)
        with urlopen(origin) as response:
            assert response.headers['X-Frame-Options'] == 'DENY'
            assert "frame-ancestors 'none'" in response.headers['Content-Security-Policy']
        from helixengine.runtime import Runtime
        from helixengine import server as server_module
        opened=[]
        monkeypatch.setattr(server_module.webbrowser,'open',lambda value:opened.append(value))
        repeated=Runtime(tmp_path/'second-launch')
        try:
            server_module.serve(repeated,port,True)
            assert opened == [origin+'/']
            assert server.poll() is None
        finally:
            repeated.close()
        settings = state['settings']
        change = dict(enabled=False, revision=settings['revision'])
        try:
            request('/api/settings',change,state['csrf_token'],'https://untrusted.example')
            raise AssertionError('Cross-origin switch accepted')
        except HTTPError as exc:
            assert exc.code == 403
        assert request()[1]['settings'] == settings
        request('/api/settings', change, state['csrf_token'])
        command = [sys.executable, '-c', "import sys; sys.stdout.buffer.write(b'line\\n'*2000); sys.stderr.buffer.write(b'warning\\n')"]
        off = subprocess.run(args + ['run','--'] + command,capture_output=True,timeout=15)
        assert off.returncode == 0
        assert off.stdout == b'line\n'*2000 and off.stderr == b'warning\n'
        state = request()[1]
        off_row = state['runs'][0]
        assert off_row['enabled'] is False and off_row['stdout_bytes'] == 10000
        request('/api/settings',dict(enabled=True,revision=state['settings']['revision']),state['csrf_token'])
        marker = tmp_path/'executions'
        code = "import pathlib,sys; p=pathlib.Path(sys.argv[1]); p.write_text(p.read_text()+'x' if p.exists() else 'x'); print('line\\n'*10000); sys.exit(7)"
        on = subprocess.run(args+['run','--',sys.executable,'-c',code,str(marker)],capture_output=True,timeout=15)
        assert on.returncode == 7 and marker.read_text() == 'x'
        state = request()[1]
        row = state['runs'][0]
        assert row['enabled'] is True and row['exit_code'] == 7
        assert row['stdout_bytes'] == 50001 and row['visible_bytes'] < row['stdout_bytes']
        assert len(state['runs']) == 2
    finally:
        server.terminate()
        try:
            server.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.communicate(timeout=5)
