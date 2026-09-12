import base64,json,os,sys,subprocess
from pathlib import Path
import pytest
from helixengine.core.evidence import Store,run,packet,reduce_stream

NATIVE_NEWLINE=os.linesep

def test_exact_binary_and_line_retrieval(tmp_path):
 s=Store(tmp_path/'s');raw=b'a\r\n\xff\x00\nlast';out=run(s,[sys.executable,'-c',f'import sys;sys.stdout.buffer.write({raw!r})'],tmp_path,'test')
 got=s.retrieve(out['receipt']);assert base64.b64decode(got['base64'])==raw
 got=s.retrieve(out['receipt'],start=1,end=1);assert got['text']=='a\r\n'
 assert s.receipt(out['receipt'])['environment_id']=='test'

def test_exit_semantics_and_raw_stderr(tmp_path):
 cli='helixengine.core.evidence'
 p=subprocess.run([sys.executable,'-m',cli,'--store',str(tmp_path/'s'),'run','--cwd',str(tmp_path),'--',sys.executable,'-c','import sys;print("failed",file=sys.stderr);sys.exit(7)'],cwd=Path(__file__).resolve().parents[2],capture_output=True,text=True)
 assert p.returncode==7
 packet=json.loads(p.stdout);assert packet['exit_code']==7 and Store(tmp_path/'s').retrieve(packet['receipt'],'stderr')['text']==f'failed{NATIVE_NEWLINE}'

def test_typed_failure_and_unknown_output_are_partial(tmp_path):
 raw=b'noise\nFAILED test_example - exact=000.100\n==== 2 failed, 211 passed in 2.3s ====\n'
 p=reduce_stream(raw,'pytest');assert p['projection_only'] and p['diagnostics'][0]['line']==2
 assert '000.100' in p['diagnostics'][0]['text']
 assert reduce_stream(b'unknown output','generic')['preview'][0]['text']=='unknown output'

def test_timeout_keeps_partial_output_and_failure(tmp_path):
 s=Store(tmp_path/'s');p=run(s,[sys.executable,'-u','-c','import time;print("partial");time.sleep(30)'],tmp_path,'test',timeout=.2)
 assert p['timed_out'] and p['exit_code']!=0 and s.retrieve(p['receipt'])['text']==f'partial{NATIVE_NEWLINE}'
 assert list((s.root/'runs').glob('*/stdout'))

def test_tamper_never_silently_trusted(tmp_path):
 s=Store(tmp_path/'s');obj=s.put(b'evidence');(s.root/'objects'/obj['sha256']).write_bytes(b'bad')
 with pytest.raises(ValueError):s.get(obj['sha256'])
 with pytest.raises(ValueError):s.put(b'evidence')
 with pytest.raises(ValueError):s.get('../outside')

def test_bounded_packet_retains_retrieval_and_watched_changes(tmp_path):
 s=Store(tmp_path/'s');(tmp_path/'a').write_text('old')
 p=run(s,[sys.executable,'-c','from pathlib import Path;Path("a").write_text("new",encoding="utf-8");print("ERROR "+"x"*20000)'],tmp_path,'test',watch=['a'])
 assert p['retrieval_required'] and len(json.dumps(p,ensure_ascii=False,separators=(',',':')).encode())<=6000
 assert p['changed_watched_files'] and len(s.retrieve(p['receipt'])['text'])>20000

def test_read_amplification_exposed_not_hidden(tmp_path):
 s=Store(tmp_path/'s');p=run(s,[sys.executable,'-c','print("line\\n"*10000,end="")'],tmp_path,'test')
 reader=Store(s.root);got=reader.retrieve(p['receipt'],start=1,end=1)
 native_line=('line'+NATIVE_NEWLINE).encode()
 assert got['bytes']==len(native_line) and got['io']['object_bytes_read']>=50000
 assert got['io']['object_read_operations']==2
 assert p['middleware_io']['staging_bytes_written']>=50000 and p['middleware_io']['object_bytes_written']>=50000
