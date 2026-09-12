"""Real-server browser smoke. Install Playwright and Chromium before running."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import urlopen
from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='helix-browser-') as temporary:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0))
            port = sock.getsockname()[1]
        url = f'http://127.0.0.1:{port}'
        command = [sys.executable,'-m','helixengine','--data-dir',temporary]
        server = subprocess.Popen(command+['serve','--port',str(port)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        child = None
        try:
            deadline=time.monotonic()+15
            while True:
                try:
                    with urlopen(url+'/api/release-state',timeout=2):
                        break
                except URLError:
                    if server.poll() is not None or time.monotonic()>deadline:
                        raise AssertionError('Server startup failed')
                    time.sleep(.1)
            with sync_playwright() as pw:
                options={'headless':True}
                if os.environ.get('BROWSER_EXECUTABLE'):
                    options['executable_path']=os.environ['BROWSER_EXECUTABLE']
                browser=pw.chromium.launch(**options)
                page=browser.new_page(viewport={'width':1440,'height':1000},accept_downloads=True)
                errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(url)
                expect(page.locator('.model-card')).to_have_count(5)
                expect(page.locator('#engine-switch')).to_be_enabled()
                assert page.locator('#engine-switch').is_checked()
                page.locator('label[for="engine-switch"]').click()
                expect(page.locator('#engine-switch')).not_to_be_checked()
                expect(page.locator('#engine-switch')).to_be_enabled()
                with urlopen(url+'/api/release-state') as r:
                    assert json.load(r)['settings']['enabled'] is False
                page.locator('label[for="engine-switch"]').click()
                expect(page.locator('#engine-switch')).to_be_checked()
                expect(page.locator('#engine-switch')).to_be_enabled()
                page.locator('[data-model="luna"]').click()
                assert page.locator('.model-card').count()==1
                assert 'Rejected' in page.locator('.model-card').inner_text()
                page.locator('[data-model="all"]').click()
                child=subprocess.Popen(command+['run','--',sys.executable,'-c',"import time;print('browser smoke',flush=True);time.sleep(2);print('row\\n'*4000)"],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
                expect(page.locator('#run-list')).to_contain_text('RUNNING')
                child.communicate(timeout=15)
                assert child.returncode==0
                expect(page.locator('#run-list')).to_contain_text('COMPLETED')
                page.locator('#pause').click()
                assert page.locator('#pause').inner_text()=='Resume view'
                page.locator('#pause').click()
                with page.expect_download() as pending:
                    page.locator('#export-button').click()
                download=pending.value
                export_path=args.output/'operational-export.json'
                download.save_as(export_path)
                exported=json.loads(export_path.read_text())
                assert 'csrf_token' not in json.dumps(exported)
                assert exported['runs'] and exported['runs'][0]['exit_code']==0
                assert page.request.get(url+'/research').status==404
                assert not page.locator('a[href^="/research"]').count()
                assert 'research ledger' not in page.locator('body').inner_text().lower()
                page.screenshot(path=str(args.output/'desktop.png'),full_page=True)
                # A frozen browser clock/expired tariff must hide existing dollar values.
                page.evaluate("stream.close(); if (state.snapshot.pricing) state.snapshot.pricing.expires_at=1; costView();")
                assert '$' not in page.locator('#cost-table').inner_text()
                page.set_viewport_size({'width':390,'height':844})
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                page.screenshot(path=str(args.output/'mobile.png'),full_page=True)
                assert errors==[],errors
                browser.close()
                (args.output/'RESULT.json').write_text(json.dumps({'passed':True,'checks':['actual HTTP switch roundtrip','SSE running and completed events','Luna rejected capsule retained','model filter','pause/resume','CSRF-free operational export','research route absent','expired tariff withheld','mobile overflow','no browser exceptions']},indent=2)+'\n')
        finally:
            if child is not None and child.poll() is None:
                child.kill();child.communicate()
            server.terminate()
            try:
                server.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill();server.communicate()


if __name__=='__main__':
    main()
