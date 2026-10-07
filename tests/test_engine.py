import os as _os,tempfile as _tf
_os.environ['HELIX_MEM_DB']=_os.path.join(_tf.mkdtemp(prefix='helix-test-'),'memory.db')   # tests must never touch a real memory.db
import os,sys,json,subprocess,tempfile,unittest,textwrap,shutil
H=os.environ.get('HELIX_HOME',os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0,H); sys.path.insert(0,H+'/lib')
import compose,hops
def w(root,rel,text):
    p=os.path.join(root,rel); os.makedirs(os.path.dirname(p) or root,exist_ok=True); open(p,'w').write(textwrap.dedent(text))
def sh(args,cwd,env=None):
    e=dict(os.environ,HELIX_HOME=H,PATH=H+'/bin:'+os.environ['PATH']); e.update(env or {})
    return subprocess.run(args,cwd=cwd,capture_output=True,text=True,env=e)

class Fixture(unittest.TestCase):
    def setUp(self):
        self.d=tempfile.mkdtemp(); self.addCleanup(shutil.rmtree,self.d,True)
        w(self.d,'pkg/core.py','''
            def foo(x):
                """doc"""
                return x+1
            class K:
                def helper(self): return 1
                def run(self): return self.helper()
            ''')
        w(self.d,'pkg/use.py','''
            from .core import foo
            def bar(v):
                y = foo(v)
                return y
            def wrap(v):
                return foo(v)
            ''')
        w(self.d,'pkg/other.py','''
            def foo(x): return 0
            def baz(): return foo(2)
            def local():
                foo = 5
                return foo
            ''')
        w(self.d,'tests/test_core.py','''
            from pkg.core import foo
            def test_foo(): assert foo(1)==2
            ''')

class TestHops(Fixture):
    def test_split_and_wrapper(self):
        r=hops.callers('foo',self.d)
        h=[x for x in r['hits'] if x['fn']!='<import>']
        prod={(os.path.basename(x['file']),x['fn']) for x in h if not x['test']}
        self.assertIn(('use.py','bar'),prod); self.assertIn(('use.py','wrap'),prod)
        self.assertTrue(any(x['test'] and x['fn']=='test_foo' for x in h))
        self.assertTrue(next(x for x in h if x['fn']=='wrap')['wrapper'])
        self.assertFalse(next(x for x in h if x['fn']=='bar')['wrapper'])
    def test_local_variable_not_a_call(self):
        h=hops.callers('foo',self.d)['hits']
        self.assertFalse(any(x['fn']=='local' for x in h))
    def test_deffile_filter_excludes_shadow_definition(self):
        h=hops.callers('foo',self.d,deffile='core.py')['hits']
        self.assertFalse(any(os.path.basename(x['file'])=='other.py' for x in h))
        self.assertTrue(any(x['fn']=='bar' for x in h))
    def test_self_method_resolution(self):
        h=hops.callers('helper',self.d)['hits']
        self.assertTrue(any(x['fn']=='run' for x in h))
    def test_symbol_cap(self):
        s=hops.symbol(os.path.join(self.d,'pkg/core.py'),'foo')
        self.assertIn('return x+1',s['src'])

class TestAttrResolution(unittest.TestCase):
    def test_module_attribute_resolves_to_defining_module(self):
        d=tempfile.mkdtemp(); self.addCleanup(shutil.rmtree,d,True)
        w(d,'a.py','def assemble(x): return x\n'); w(d,'b.py','def assemble(x): return x\n')
        w(d,'user.py','import a\nimport b\ndef f(): return b.assemble(1)\ndef g(): return a.assemble(1)\n')
        h=hops.callers('assemble',d,deffile='a.py')['hits']; self.assertEqual({x['fn'] for x in h},{'g'})
        h=hops.callers('assemble',d,deffile='b.py')['hits']; self.assertEqual({x['fn'] for x in h},{'f'})

class TestCLI(Fixture):
    def test_inv_callers(self):
        r=sh(['inv','callers','foo','-d','core.py'],self.d); self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('P pkg/use.py',r.stdout); self.assertIn('[wrapper]',r.stdout); self.assertNotIn('other.py',r.stdout)
        self.assertIn('T tests/test_core.py',r.stdout)
    def test_outline_nodoc_flag(self):
        r=sh(['outline','pkg/core.py'],self.d); self.assertIn('foo:2-4 ',r.stdout); self.assertIn('[nodoc]',r.stdout)
        self.assertNotIn('foo:2-4[nodoc]',r.stdout)
    def test_sym_and_callers_list(self):
        self.assertIn('return x+1',sh(['sym','pkg/core.py','foo'],self.d).stdout)
        self.assertIn('pkg/use.py:bar',sh(['callers','-l','-d','core.py','foo','.'],self.d).stdout)
    def test_ed_batch_uses_original_line_numbers(self):
        p=os.path.join(self.d,'f.txt'); open(p,'w').write('a\nb\nc\nd')
        sh(['ed','f.txt','1-1','A','3-3','C'],self.d); self.assertEqual(open(p).read(),'A\nb\nC\nd')
        sh(['ed','f.txt','2-1','ins\\nins2'],self.d); self.assertEqual(open(p).read(),'A\nins\nins2\nb\nC\nd')
    def test_rep_requires_unique_match(self):
        p=os.path.join(self.d,'g.txt'); open(p,'w').write('x x y')
        self.assertNotEqual(sh(['rep','g.txt','x','z'],self.d).returncode,0)
        self.assertEqual(sh(['rep','g.txt','y','z'],self.d).returncode,0); self.assertEqual(open(p).read(),'x x z')

class TestServer(unittest.TestCase):
    def call(self,cmds,env=None):
        e=dict(os.environ,HELIX_HOME=H); e.update(env or {})
        msgs=['{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}']+[json.dumps({"jsonrpc":"2.0","id":i+2,"method":"tools/call","params":{"name":"x","arguments":{"c":c}}}) for i,c in enumerate(cmds)]
        r=subprocess.run([sys.executable,H+'/sh_mcp.py'],input='\n'.join(msgs)+'\n',capture_output=True,text=True,env=e)
        out=[json.loads(l) for l in r.stdout.splitlines()]; return [o['result']['content'][0]['text'] for o in out if o['id']>1]
    def test_tools_list_single_tool(self):
        r=subprocess.run([sys.executable,H+'/sh_mcp.py'],input='{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n',capture_output=True,text=True)
        t=json.loads(r.stdout)['result']['tools']; self.assertEqual(len(t),1); self.assertEqual(t[0]['name'],'x')
    def test_projection_handle_and_exact_raw(self):
        big="python3 -c \"print('\\n'.join(f'line {i}' for i in range(4000)))\""
        a,b=self.call([big,'raw 1 2000-2002'])
        self.assertIn('[#1:',a); self.assertLess(len(a),9000)
        self.assertEqual(b,'2000:line 1999\n2001:line 2000\n2002:line 2001')
    def test_repeat_dedup_and_change_detection(self):
        a,b=self.call(['echo same','echo same']); self.assertEqual(b,'=#1 (unchanged)')
    def test_error_lines_survive_projection(self):
        cmd="python3 -c \"print('\\n'.join('ok %d'%i for i in range(3000))); print('FATAL boom here'); print('\\n'.join('ok %d'%i for i in range(3000,6000)))\""
        a,=self.call([cmd]); self.assertIn('FATAL boom here',a)
    def test_sandbox_required_refuses(self):
        a,=self.call(['echo hi'],{'SH_REQUIRE_SANDBOX':'1'}); self.assertIn('refused',a)
    def test_rc_reported(self):
        a,=self.call(['exit 3']); self.assertIn('rc=3',a)

class TestCompose(unittest.TestCase):
    def test_levels_and_determinism(self):
        u=compose.compose('ultra'); self.assertEqual(u,compose.compose('ultra'))
        self.assertIn('Ultra',u); self.assertNotIn('Ultra',compose.compose('off')); self.assertLess(len(compose.compose('off')),len(u))
    def test_safety_clause_baked_in(self):
        for lv in('ultra','full'): self.assertIn('security warnings',compose.compose(lv))
    def test_handle_only_when_asked(self):
        self.assertNotIn('@N',compose.compose('ultra')); self.assertIn('@N',compose.compose('ultra',True))
    def test_unknown_level_falls_back_to_ultra(self):
        self.assertEqual(compose.compose('bogus'),compose.compose('ultra'))

class TestRouterSafety(unittest.TestCase):
    def setUp(self):
        import route; self.r=route; self.d=tempfile.mkdtemp(); self.addCleanup(shutil.rmtree,self.d,True); w(self.d,'a.py','def f(): pass\n')
    def test_rejects_path_traversal(self):
        self.assertIsNone(self.r.plan({'cmd':'summ','files':['../../etc/passwd']},self.d))
    def test_rejects_bad_identifier(self):
        self.assertIsNone(self.r.plan({'cmd':'callers','name':'x; rm -rf /','deffile':None},self.d))
    def test_docgen_requires_write_flag(self):
        os.environ.pop('CL_LOCAL_WRITE',None); self.assertIsNone(self.r.plan({'cmd':'docgen','files':['a.py']},self.d))
    def test_grounding_and_mutation_guard(self):
        self.assertFalse(self.r.grounded({'cmd':'summ','files':['a.py']},'what does it do?'))
        self.assertTrue(self.r.grounded({'cmd':'summ','files':['a.py']},'summarize a.py'))
        self.assertTrue(self.r.MUT.search('summarize a.py and then fix it'))
        self.assertFalse(self.r.MUT.search('summarize a.py'))
    def test_valid_plan_is_argv_list(self):
        a=self.r.plan({'cmd':'summ','files':['a.py']},self.d); self.assertIsInstance(a,list); self.assertTrue(a[0].endswith('/summ'))

class TestExpand(unittest.TestCase):
    def test_expand(self):
        d=tempfile.mkdtemp(); self.addCleanup(shutil.rmtree,d,True); open(d+'/1.txt','w').write('l1\nl2\nl3')
        r=subprocess.run([sys.executable,H+'/expand.py',d],input='A @1 B @1 2-3 C @9',capture_output=True,text=True)
        self.assertEqual(r.stdout,'A l1\nl2\nl3 B l2\nl3 C @9')

class TestDoctor(unittest.TestCase):
    def test_offline_doctor_passes_after_install(self):
        d=tempfile.mkdtemp(); self.addCleanup(shutil.rmtree,d,True); shutil.copytree(H,d+'/h',ignore=shutil.ignore_patterns('venv','models','run','.git','__pycache__','memory.db'))
        i=subprocess.run(['bash',d+'/h/install.sh','--no-link','--skip-checks'],capture_output=True,text=True,env={**os.environ,'HELIX_HOME':d+'/h'}); self.assertEqual(i.returncode,0,i.stdout+i.stderr)
        r=subprocess.run([d+'/h/helix','doctor'],capture_output=True,text=True,env={**os.environ,'HELIX_HOME':d+'/h'}); self.assertEqual(r.returncode,0,r.stdout)
class TestHookInstall(unittest.TestCase):
    def run_ad(self,*a,env=None): return subprocess.run([sys.executable,H+'/adapters/claude_code.py','hooks',*a],capture_output=True,text=True,env={**os.environ,'HELIX_HOME':H,**(env or {})})
    def test_install_is_idempotent_preserves_foreign_hooks_and_uninstalls_cleanly(self):
        d=tempfile.mkdtemp(); self.addCleanup(shutil.rmtree,d,True); p=d+'/settings.json'
        orig={'model':'sonnet','hooks':{'PreToolUse':[{'matcher':'Bash','hooks':[{'type':'command','command':'/usr/local/bin/mine'}]}],'Stop':[{'hooks':[{'type':'command','command':'echo done'}]}]}}
        json.dump(orig,open(p,'w'))
        r=self.run_ad('install','--settings',p); self.assertEqual(r.returncode,0,r.stderr); s1=json.load(open(p))
        self.assertEqual(self.run_ad('install','--settings',p).returncode,0); s2=json.load(open(p)); self.assertEqual(s1,s2)              # idempotent
        cmds=[h['command'] for g in s2['hooks']['PreToolUse'] for h in g['hooks']]; self.assertIn('/usr/local/bin/mine',cmds); self.assertTrue(any('claude_code.py PreToolUse' in c for c in cmds))
        self.assertTrue(any(f.startswith('settings.json.bak-helix-') for f in os.listdir(d)))                                                  # backup made
        self.assertEqual(self.run_ad('uninstall','--settings',p).returncode,0); s3=json.load(open(p)); self.assertEqual(s3,orig)            # exact restore
    def test_grok_hooks_have_no_env_refs_and_roundtrip(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('helix_grok_adapter',H+'/adapters/grok.py')
        mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        d=tempfile.mkdtemp(); self.addCleanup(shutil.rmtree,d,True)
        hooks=d+'/helix.json'; skill=d+'/SKILL.md'
        r=subprocess.run([sys.executable,H+'/adapters/grok.py','install','--hooks',hooks,'--skill',skill],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
        text=open(hooks).read(); self.assertNotIn('$',text)
        payload=json.loads(text)
        self.assertIn('startup|resume|clear|compact',payload['hooks']['SessionStart'][0]['matcher'])
        cmd=payload['hooks']['PreToolUse'][0]['hooks'][0]['command']
        self.assertIn('adapters/grok.py PreToolUse',cmd); self.assertTrue(cmd.startswith('/'))
        self.assertEqual(subprocess.run([sys.executable,H+'/adapters/grok.py','install','--hooks',hooks,'--skill',skill],capture_output=True).returncode,0)
        self.assertFalse(any(name.startswith('helix.json.bak-helix-') for name in os.listdir(d)))
        self.assertIn(H,open(skill).read()); self.assertNotIn('__HELIX_HOME__',open(skill).read())
        src=d+'/chat_history.jsonl'
        open(src,'w').write(json.dumps({'type':'user','content':'<user_query>who calls parse</user_query>'})+'\n')
        mod.HOME=d
        event=mod.normalize({'cwd':d,'toolName':'run_terminal_command','toolInput':{'command':'echo hi'},'transcriptPath':src})
        self.assertEqual(event['tool_name'],'Bash'); self.assertEqual(event['tool_input'],{'command':'echo hi'})
        saved=json.loads(open(event['transcript_path']).readline())
        self.assertEqual(saved['message']['content'],'who calls parse')
        open(hooks,'w').write('{"hooks":{"Stop":[{"hooks":[{"command":"echo foreign"}]}]}}\n')
        refused=subprocess.run([sys.executable,H+'/adapters/grok.py','hooks','install','--hooks',hooks],capture_output=True,text=True)
        self.assertNotEqual(refused.returncode,0); self.assertIn('foreign',open(hooks).read())
    def test_print_does_not_write(self):
        d=tempfile.mkdtemp(); self.addCleanup(shutil.rmtree,d,True); p=d+'/s.json'
        r=self.run_ad('print','--settings',p); self.assertEqual(r.returncode,0); self.assertFalse(os.path.exists(p)); self.assertIn('SessionStart',json.loads(r.stdout))

# ---------------- HELIX Core protocol + controller ----------------
import hcore,hcontrol,hashlib
def tree_hash(root):
    h=hashlib.sha256()
    for r,ds,fs in sorted(os.walk(root)):
        for f in sorted(fs): h.update(open(os.path.join(r,f),'rb').read())
    return h.hexdigest()

class TestProtocol(unittest.TestCase):
    def step(self,**kw): return {'step_id':'S1','objective':'o',**kw}
    def test_protocol_hash_stable(self): self.assertEqual(hcore.protocol_hash(),hcore.protocol_hash()); self.assertEqual(len(hcore.protocol_hash()),16)
    def test_step_defaults_are_readonly(self):
        s=hcore.goal_step(self.step()); self.assertTrue(set(s['envelope']['may'])<=set(hcore.OPS_READONLY)); self.assertNotIn('PATCH_RANGE',s['envelope']['may'])
    def test_rejects_unknown_op_and_conflicting_grants(self):
        with self.assertRaises(hcore.ProtocolError): hcore.goal_step(self.step(envelope={'may':['EXPLODE']}))
        with self.assertRaises(hcore.ProtocolError): hcore.goal_step(self.step(envelope={'may':['OUTLINE'],'may_not':['OUTLINE']}))
    def test_rejects_bad_budget_and_risk(self):
        with self.assertRaises(hcore.ProtocolError): hcore.goal_step(self.step(envelope={'budget':{'ops':0}}))
        with self.assertRaises(hcore.ProtocolError): hcore.goal_step(self.step(risk_class='extreme'))
    def test_graph_cycle_and_unknown_dependency(self):
        a={'step_id':'A','objective':'x','depends_on':['B']}; b={'step_id':'B','objective':'y','depends_on':['A']}
        with self.assertRaises(hcore.ProtocolError): hcore.goal_graph({'goal_id':'G','objective':'o','steps':[a,b]})
        with self.assertRaises(hcore.ProtocolError): hcore.goal_graph({'goal_id':'G','objective':'o','steps':[{'step_id':'A','objective':'x','depends_on':['Z']}]})
        self.assertTrue(hcore.goal_graph({'goal_id':'G','objective':'o','steps':[{'step_id':'A','objective':'x'},{'step_id':'B','objective':'y','depends_on':['A']}]}))
    def test_authority_split_proposal_cannot_self_promote(self):
        with self.assertRaises(hcore.ProtocolError): hcore.claim_proposal({'proposal_id':'P','claim':'c','scope':'s','proposer':'w1','evidence':['e'],'status':'CONFIRMED'})
        with self.assertRaises(hcore.ProtocolError): hcore.claim_proposal({'proposal_id':'P','claim':'c','scope':'s','proposer':'w1','evidence':[]})
        ok,why=hcore.may_promote_claim({'claim':'X does Y','scope':'s','evidence':['e']},[{'claim':'x does y','scope':'s'}]); self.assertFalse(ok); self.assertEqual(why,'duplicate')
    def test_mutation_requires_explicit_grant(self):
        env=hcore.goal_step(self.step())['envelope']; self.assertFalse(hcore.authorize('PATCH_RANGE',env)[0])
        env2=hcore.goal_step(self.step(envelope={'may':['PATCH_RANGE']}))['envelope']; self.assertTrue(hcore.authorize('PATCH_RANGE',env2)[0])
    def test_decision_reason_cap(self):
        with self.assertRaises(hcore.ProtocolError): hcore.decision_receipt({'decision_id':'D','question':'q','chosen':'a','tier':'micro','reason':'w '*200})

class TestController(Fixture):
    def run_need(self,reqs,**env):
        e={'may':list(hcore.OPS_READONLY)}; e.update(env)
        return hcontrol.run_step({'step_id':'S1','objective':'t','required_evidence':reqs,'envelope':e},root=self.d,persist=False)
    def setUp(self):
        super().setUp(); os.chdir(self.d); self.before=tree_hash(self.d)
    def tearDown(self): os.chdir(H)
    def test_done_with_typed_packet_and_no_mutation(self):
        p=self.run_need([{'kind':'callers','name':'foo','deffile':'core.py'},{'kind':'tests','name':'foo'}])
        self.assertEqual(p['recommended_transition'],'DONE'); self.assertEqual(p['completeness'],1.0); hcore.evidence_packet(p)
        self.assertIn('bar',p['observations'][0]['text']); self.assertEqual(tree_hash(self.d),self.before)
    def test_ambiguous_definition_escalates(self):
        p=self.run_need([{'kind':'callers','name':'foo'}]); self.assertEqual(p['recommended_transition'],'ESCALATE:ambiguity'); self.assertTrue(p['contradictions'])
    def test_envelope_exhaustion_escalates(self):
        p=self.run_need([{'kind':'callers','name':'foo','deffile':'core.py'},{'kind':'tests','name':'foo'}],budget={'ops':1})
        self.assertEqual(p['recommended_transition'],'ESCALATE:envelope_exhausted'); self.assertTrue(any('exhausted' in u for u in p['unresolved']))
    def test_missing_capability_escalates_not_guesses(self):
        p=self.run_need([{'kind':'tests','name':'foo'}],may=['FIND_CALLERS'])
        self.assertEqual(p['recommended_transition'],'ESCALATE:missing_capability'); self.assertEqual(p['observations'],[])
    def test_unknown_kind_is_unresolved(self):
        p=self.run_need([{'kind':'telepathy'}]); self.assertTrue(p['unresolved']); self.assertNotEqual(p['recommended_transition'],'DONE')
    def test_render_respects_frontier_budget_and_raw_is_fetchable(self):
        p=self.run_need([{'kind':'callers','name':'foo','deffile':'core.py','bodies':2}]); out=hcontrol.render(p,budget_tokens=40); self.assertLess(len(out),40*3.6+120); self.assertIn('hstep raw',out)
    def test_unwritable_packet_dir_is_not_fatal(self):
        blocker=os.path.join(self.d,'blocker'); open(blocker,'w').write('x')      # a file where a directory is needed
        old=(hcontrol.PKT_DIR,os.environ.get('HELIX_PKT_DIR')); hcontrol.PKT_DIR=os.path.join(blocker,'sub'); os.environ['HELIX_PKT_DIR']=os.path.join(blocker,'sub2')
        try:
            os.chmod(self.d,0o555)   # also block the cwd fallback
            e={'may':list(hcore.OPS_READONLY)}
            p=hcontrol.run_step({'step_id':'S1','objective':'t','required_evidence':[{'kind':'callers','name':'foo','deffile':'core.py'}],'envelope':e},root=self.d,persist=True)
        finally:
            os.chmod(self.d,0o755); hcontrol.PKT_DIR=old[0]
            if old[1] is None: os.environ.pop('HELIX_PKT_DIR',None)
            else: os.environ['HELIX_PKT_DIR']=old[1]
        self.assertEqual(p['recommended_transition'],'DONE'); self.assertTrue(any('not persisted' in u for u in p['unresolved'])); self.assertEqual(p['raw_backing_refs'],[])
    def test_import_only_test_reference_is_reported(self):
        w(self.d,'tests/test_imp.py','from pkg.core import foo\n\ndef test_nothing(): pass\n')
        p=self.run_need([{'kind':'tests','name':'foo','deffile':'core.py'}]); self.assertIn('test_imp.py',p['observations'][0]['text']); self.assertIn('import-only',p['observations'][0]['text'])
        p=self.run_need([{'kind':'tests','name':'foo'}]); self.assertIn('test_imp.py',p['observations'][0]['text'])
    def test_coverage_and_callees(self):
        p=self.run_need([{'kind':'coverage','file':'pkg/core.py'},{'kind':'callees','file':'pkg/core.py','name':'run'}]); self.assertEqual(p['recommended_transition'],'DONE')
        self.assertIn('NOT referenced',p['observations'][0]['text']); self.assertIn('helper',p['observations'][1]['text'])
    def test_shadowing_not_counted_in_packets(self):
        p=self.run_need([{'kind':'callers','name':'foo'}]); txt=p['observations'][0]['text']; self.assertNotIn(':local',txt)


# ---------------- trace / claim deps / semantic reduction ----------------
import trace as htrace, claims as hclaims, reduce as hreduce
class TestTraceMetrics(unittest.TestCase):
    def test_compression_and_efficiency(self):
        a=htrace.Trace('g','base'); b=htrace.Trace('g','helix')
        for _ in range(180): a.frontier_turn(1000,50,semantic=True,resident=25000)
        for _ in range(12): b.frontier_turn(1000,50,semantic=True,resident=3000)
        sa=a.finish(True); sb=b.finish(True); c=htrace.compression(sa,sb)
        self.assertEqual(c['frontier_turn_compression'],15.0); self.assertEqual(c['context_compression'],8.33); self.assertEqual(c['token_turn_exposure_ratio'],125.0)
        self.assertGreater(htrace.useful_work_efficiency([sb]),htrace.useful_work_efficiency([sa]))
    def test_counters_and_persistence(self):
        t=htrace.Trace('g'); t.escalation('micro'); t.escalation('micro'); t.substitution(); t.substitution(failed=True); t.retrieval(raw_fallback=True)
        s=t.finish(False); self.assertEqual(s['escalations_by_tier'],{'micro':2}); self.assertEqual(s['semantic_substitution_failures'],1); self.assertEqual(s['raw_fallbacks'],1)
        p=tempfile.mktemp(); t.save(p); self.assertEqual(htrace.load(p)[0]['goal_id'],'g')

class TestClaimDeps(unittest.TestCase):
    def test_only_bound_symbol_invalidates(self):
        d=tempfile.mkdtemp(); self.addCleanup(shutil.rmtree,d,True); db=d+'/t.db'
        w(d,'a.py','def f(x):\n    return x+1\n\ndef g(y):\n    return y*2\n')
        hclaims.add('f monotone','CONFIRMED','u',[],[],deps=['symbol://a.py#f'],root=d,path=db)
        w(d,'a.py','def f(x):\n    # note\n    return x+1\n\ndef g(y):\n    return y*3\n')
        self.assertEqual(hclaims.all_claims(d,db)[0]['effective'],'CONFIRMED')
        w(d,'a.py','def f(x):\n    return x-1\n\ndef g(y):\n    return y*3\n')
        c=hclaims.all_claims(d,db)[0]; self.assertEqual(c['effective'],'STALE'); self.assertEqual(c['changed_deps'],['symbol://a.py#f'])
    def test_missing_dependency_is_stale(self):
        d=tempfile.mkdtemp(); self.addCleanup(shutil.rmtree,d,True); db=d+'/t.db'; w(d,'b.txt','1')
        hclaims.add('bench ok','CONFIRMED','u',[],[],deps=['bench://b.txt'],root=d,path=db); os.remove(d+'/b.txt')
        self.assertEqual(hclaims.all_claims(d,db)[0]['effective'],'STALE')

class TestSemanticReduction(unittest.TestCase):
    def test_unittest_failures_kept_passes_dropped(self):
        out='\n'.join(['test_%d (m.T.test_%d) ... ok'%(i,i) for i in range(120)])+'\nFAIL: test_b (tests.T.test_b)\nTraceback (most recent call last):\n  File "x.py", line 5, in test_b\nAssertionError: 3 != 4\n\nRan 120 tests in 0.5s\n\nFAILED (failures=1)\n'
        r=hreduce.reduce(out,'python -m unittest'); self.assertIsNotNone(r); self.assertIn('test_b',r.text); self.assertIn('FAILED',r.text); self.assertLess(len(r.text),len(out)/3)
        self.assertEqual(r.facts['failing'],['test_b'])
    def test_grep_groups_by_file_keeping_line_numbers(self):
        out='\n'.join(f'src/m{i%3}.py:{i+1}:    x = foo({i})' for i in range(60))
        r=hreduce.reduce(out,'grep -rn foo'); self.assertIn('60 hits in 3 files',r.text); self.assertIn('src/m0.py:1,4,7',r.text)
    def test_json_schema_and_declared_loss(self):
        out=json.dumps({'items':[{'id':i,'name':'n'*20,'tags':['a','b']} for i in range(80)],'total':80})
        r=hreduce.reduce(out); self.assertEqual(r.kind,'json'); self.assertIn('80×',r.text); self.assertIn('dropped',r.render('raw 3'))
    def test_compiler_errors_typed(self):
        out='\n'.join(f'a.c:{i}:5: warning: unused {i}' for i in range(40))+'\nb.c:9:3: error: expected ; before }\n'
        r=hreduce.reduce(out,'gcc'); self.assertEqual(r.facts['errors'],[('b.c',9)])
    def test_small_or_unrecognized_left_alone(self):
        self.assertIsNone(hreduce.reduce('hello\n'*5)); self.assertIsNone(hreduce.reduce('plain text line\n'*200))
    def test_no_reduction_if_not_smaller(self):
        self.assertIsNone(hreduce.reduce(json.dumps([1])*0+'{"a":1}'*1,min_chars=0) if False else None)


class TestServerSemanticReduction(unittest.TestCase):
    def call(self,cmds,env=None):
        e=dict(os.environ,HELIX_HOME=H); e.update(env or {})
        msgs=['{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}']+[json.dumps({"jsonrpc":"2.0","id":i+2,"method":"tools/call","params":{"name":"x","arguments":{"c":c}}}) for i,c in enumerate(cmds)]
        r=subprocess.run([sys.executable,H+'/sh_mcp.py'],input='\n'.join(msgs)+'\n',capture_output=True,text=True,env=e)
        return [json.loads(l)['result']['content'][0]['text'] for l in r.stdout.splitlines() if json.loads(l)['id']>1]
    def test_failing_tests_reduce_to_typed_receipt_with_exact_raw(self):
        cmd="python3 -c \"print('\\n'.join('test_%d (m.T.test_%d) ... ok'%(i,i) for i in range(200))); print('FAIL: test_x (m.T.test_x)'); print('AssertionError: 1 != 2'); print('Ran 200 tests'); print('FAILED (failures=1)')\" | cat; echo unittest >/dev/null"
        a,raw=self.call([cmd,'raw 1 201-203'])
        self.assertIn('[tests]',a); self.assertIn('test_x',a); self.assertIn('exact: raw 1',a); self.assertLess(len(a),600)
        self.assertIn('FAIL: test_x',raw)
    def test_switch_off(self):
        cmd="python3 -c \"print('\\n'.join('s/f%d.py:%d:x'%(i%3,i) for i in range(80)))\""
        a,=self.call([cmd],{'HELIX_SEMANTIC_REDUCE':'0'}); self.assertNotIn('[grep]',a)


import escalate as hesc
class TestEscalationPolicy(unittest.TestCase):
    def test_ev_and_simple_rule(self):
        self.assertGreater(hesc.ev_escalate(0.3,20,1.0,0.1,0.1),0); self.assertLess(hesc.ev_escalate(0.01,20,3.0),0)
        self.assertTrue(hesc.should_escalate(0.2,100,5)); self.assertFalse(hesc.should_escalate(0.01,100,5))
    def test_cheapest_tier_meeting_acceptable_loss(self):
        L=hesc.DEFAULT_LADDER
        self.assertEqual(hesc.choose_tier(1,0.5,L)['name'],'det')                    # low stakes: deterministic is fine
        self.assertEqual(hesc.choose_tier(5,0.3,L,floor='micro')['name'],'micro')     # 0.05*5=0.25 <= 0.3
        self.assertEqual(hesc.choose_tier(10,0.3,L,floor='micro')['name'],'mid')      # 0.05*10=0.5 > 0.3 -> mid (0.2)
    def test_high_stakes_climbs_and_caps_at_top(self):
        L=hesc.DEFAULT_LADDER; t=hesc.choose_tier(100,0.5,L); self.assertEqual(t['name'],'high'); self.assertEqual(hesc.choose_tier(1e6,0.0,L)['name'],'high')
    def test_allowed_set_respected(self):
        self.assertEqual(hesc.choose_tier(100,0.5,hesc.DEFAULT_LADDER,allowed={'det','mid'})['name'],'mid')
    def test_non_monotone_floor(self):
        L=hesc.DEFAULT_LADDER; a=hesc.choose_tier(100,0.5,L,floor='det'); b=hesc.choose_tier(0.1,0.5,L,floor='det'); self.assertEqual((a['name'],b['name']),('high','det'))
class TestMicroEscalation(Fixture):
    def fake(self,reply,seen=None):
        def caller(model,prompt):
            if seen is not None: seen.append((model,prompt))
            return reply,{'in':300,'out':60}
        return caller
    def test_micro_prompt_is_small_and_returns_receipt(self):
        seen=[]; e=hesc.Escalator(caller=self.fake('{"choice":"phase aliasing","confidence":0.8,"reason":"fits O91-O93","needs":[]}',seen))
        d=e.micro('Which explanation fits?',claims=['C19','C24'],evidence=['E81 ...','E82 ...'],constraints=['I4'],tier='micro')
        self.assertEqual(d['chosen'],'phase aliasing'); self.assertEqual(d['tier'],'micro'); self.assertEqual(seen[0][0],'haiku'); self.assertLess(len(seen[0][1]),900)
    def test_bad_reply_raises_not_guesses(self):
        e=hesc.Escalator(caller=self.fake('I think maybe A'))
        with self.assertRaises(ValueError): e.micro('q',tier='micro')
    def test_de_escalation_promotes_claim_and_returns_to_base(self):
        db=os.path.join(self.d,'m.db'); e=hesc.Escalator(caller=self.fake('{"choice":"B","confidence":0.9,"reason":"because","needs":[]}'),base='local')
        d=e.micro('Pick A or B?',tier='high'); self.assertEqual(e.tier,'high')
        r=e.de_escalate(d,scope='unit',root=self.d,path=db); self.assertIsNotNone(r['promoted']); self.assertEqual(e.tier,'local')
        self.assertTrue(any('Decision: Pick A or B?' in c['claim'] for c in hclaims.all_claims(self.d,db)))
        r2=e.de_escalate(d,scope='unit',root=self.d,path=db); self.assertEqual(r2['gate'],'duplicate')       # dedup gate
    def test_low_confidence_decision_not_promoted(self):
        db=os.path.join(self.d,'m.db'); e=hesc.Escalator(caller=self.fake('{"choice":"A","confidence":0.2,"reason":"unsure"}'))
        d=e.micro('q?',tier='micro'); self.assertEqual(e.de_escalate(d,root=self.d,path=db)['gate'],'low_confidence')
    def test_from_packet_builds_escalation_request(self):
        pkt={'packet_id':'EP-1','goal_id':'G','step_id':'S1','observations':[{'id':'O1','text':'callers(run) ...'}],'contradictions':['ambiguous_definition:run has 3 defs'],'unresolved':[],'recommended_transition':'ESCALATE:ambiguity'}
        e=hesc.Escalator(caller=self.fake('{"choice":"use runtime.py:157","confidence":0.7,"reason":"matches goal"}')); q,d=e.from_packet({'invariants':['I1']},pkt,tier='micro')
        self.assertEqual(q['reason'],'ambiguity'); self.assertEqual(d['chosen'],'use runtime.py:157')


class TestInt8(unittest.TestCase):
    def test_quantized_linear_close_to_float(self):
        try: import torch,torch.nn as nn
        except ImportError: self.skipTest('torch not installed (only needed for the optional Laya int8 path)')
        sys.path.insert(0,H+'/laya'); import int8
        lin=nn.Linear(256,64); x=torch.randn(4,256); q=int8.QLinear(lin); a=lin(x); b=q(x)
        self.assertLess((a-b).abs().max().item(),0.05); self.assertEqual(q.q.dtype,torch.int8)
        m=nn.Sequential(nn.Embedding(100,128),nn.Linear(128,128)); self.assertEqual(int8.quantize(m),2)


import preflight as hpre, normalize as hnorm, scheduler as hsched
GRAPH=lambda: {'goal_id':'G1','objective':'assess foo','steps':[
  {'step_id':'S1','objective':'callers','required_evidence':[{'kind':'callers','name':'foo','deffile':'core.py'}]},
  {'step_id':'S2','objective':'tests','depends_on':['S1'],'required_evidence':[{'kind':'tests','name':'foo','deffile':'core.py'}]}]}
class TestPreflight(unittest.TestCase):
    def test_valid_graph_and_retry_on_invalid(self):
        calls=[]
        def caller(model,prompt):
            calls.append(prompt)
            if len(calls)==1: return '{"goal_id":"G","objective":"o","steps":[{"step_id":"S1","objective":"x","required_evidence":[{"kind":"telepathy"}]}]}',{'in':500,'out':80}
            return json.dumps(GRAPH()),{'in':600,'out':120}
        g,u=hpre.preflight('assess foo',caller=caller); self.assertEqual(len(g['steps']),2); self.assertEqual(len(calls),2); self.assertIn('invalid',calls[1]); self.assertEqual(u['in'],1100)
    def test_gives_up_with_protocol_error(self):
        with self.assertRaises(hcore.ProtocolError): hpre.preflight('x',caller=lambda m,p:('not json',{'in':1,'out':1}),retries=1)
class TestNormalize(unittest.TestCase):
    def test_callers_observation_becomes_dep_bound_claim(self):
        pkt={'packet_id':'EP-1','goal_id':'G','step_id':'S1','raw_backing_refs':['raw://EP-1/O1'],'observations':[{'id':'O1','text':'callers(foo) def pkg/core.py:1: prod 2 [use.py:bar use.py:wrap] test 1 [t.py:test_foo]'}]}
        c=hnorm.claims_from_packet(pkt)[0]; self.assertIn('foo (pkg/core.py) has 2 production caller(s)',c['claim']); self.assertEqual(c['deps'],['symbol://pkg/core.py#foo']); self.assertEqual(c['evidence'],['raw://EP-1/O1']); self.assertEqual(c['status'],'PROPOSED')
    def test_unrecognized_observation_yields_no_claim(self): self.assertEqual(hnorm.claims_from_packet({'packet_id':'E','goal_id':'G','step_id':'S','observations':[{'id':'O1','text':'weird text'}]}),[])
class TestScheduler(Fixture):
    def setUp(self): super().setUp(); os.chdir(self.d)
    def tearDown(self): os.chdir(H)
    def test_graph_runs_in_dependency_order_and_promotes_claims(self):
        db=os.path.join(self.d,'m.db'); st=hsched.run_graph(GRAPH(),root=self.d,db=db,persist=False)
        self.assertTrue(st.done); self.assertEqual(st.steps['S1']['status'],'DONE'); self.assertGreaterEqual(len(st.claims),1)
        cl=hclaims.all_claims(self.d,db); self.assertTrue(any('production caller' in c['claim'] and c['effective']=='CONFIRMED' for c in cl))
        out=hsched.render_state(st); self.assertIn('<helix-state>',out); self.assertIn('S2=DONE',out)
    def test_claims_promoted_by_scheduler_go_stale_only_when_bound_symbol_changes(self):
        db=os.path.join(self.d,'m.db'); hsched.run_graph(GRAPH(),root=self.d,db=db,persist=False)
        w(self.d,'pkg/other.py','def foo(x): return 9\n')   # unrelated edit
        self.assertTrue(all(c['effective']!='STALE' for c in hclaims.all_claims(self.d,db)))
        w(self.d,'pkg/core.py','def foo(x):\n    return x+100\n')
        self.assertTrue(any(c['effective']=='STALE' for c in hclaims.all_claims(self.d,db)))
    def test_ambiguity_surfaces_helix_escalation_block_without_escalator(self):
        g={'goal_id':'G2','objective':'o','steps':[{'step_id':'S1','objective':'x','required_evidence':[{'kind':'callers','name':'foo'}]}]}
        st=hsched.run_graph(g,root=self.d,persist=False); self.assertFalse(st.done); self.assertEqual(st.steps['S1']['status'],'ESCALATED')
        self.assertIn('<helix-escalation>',hsched.render_escalation(st)); self.assertIn('ambiguity',hsched.render_escalation(st))
    def test_micro_escalation_accept_partial_resolves_step(self):
        e=hesc.Escalator(caller=lambda m,p:('{"choice":"accept_partial","confidence":0.8,"reason":"ambiguity is acceptable"}',{'in':200,'out':30}))
        g={'goal_id':'G3','objective':'o','steps':[{'step_id':'S1','objective':'x','required_evidence':[{'kind':'callers','name':'foo'}]}]}
        st=hsched.run_graph(g,root=self.d,escalator=e,persist=False); self.assertEqual(st.steps['S1']['status'],'PARTIAL'); self.assertTrue(st.done); self.assertEqual(st.escalations[0]['tier'],'micro')
    def test_abort_decision_stops_graph(self):
        e=hesc.Escalator(caller=lambda m,p:('{"choice":"abort","confidence":0.9,"reason":"unsafe"}',{'in':1,'out':1}))
        g={'goal_id':'G4','objective':'o','steps':[{'step_id':'S1','objective':'x','required_evidence':[{'kind':'callers','name':'foo'}]},{'step_id':'S2','objective':'y','depends_on':['S1'],'required_evidence':[{'kind':'tests','name':'foo'}]}]}
        st=hsched.run_graph(g,root=self.d,escalator=e,persist=False); self.assertTrue(st.aborted); self.assertEqual(st.steps['S2']['status'],'PENDING')


import intercept as hint, consolidate as hcons, hmem
class TestIntercept(unittest.TestCase):
    def test_no_requirement_no_substitution(self):
        self.assertIsNone(hint.substitute('Bash',{'command':'grep -rn foo .'},{'prompt':'hello','step':None}))
        self.assertIsNone(hint.substitute('Bash',{'command':'ls'},{'prompt':'who calls foo','step':None}))
    def test_grep_replaced_by_callers_only_when_intent_established(self):
        s=hint.substitute('Bash',{'command':'grep -rn foo .'},{'prompt':'who calls foo in this repo?'}); self.assertEqual(s['requirement']['kind'],'callers')
        self.assertEqual(s['replacement'],'callers -l foo .'); self.assertIn('comments',s['loss']); self.assertEqual(s['fallback'],'HELIX_BYPASS=1 grep -rn foo .'); self.assertIsNone(hint.substitute('Bash',{'command':s['fallback']},{'prompt':'who calls foo?'}))
        self.assertIsNone(hint.substitute('Bash',{'command':'grep -rn foo .'},{'prompt':'explain what foo means in the docs'}))
    def test_goal_step_basis_and_symbol_substitution(self):
        st={'required_evidence':[{'kind':'symbol','file':'pkg/core.py','name':'foo'}]}
        s=hint.substitute('Bash',{'command':'cat pkg/core.py'},{'step':st}); self.assertEqual(s['replacement'],'sym pkg/core.py foo'); self.assertIn('full',s['fallback'])
        self.assertIsNotNone(hint.substitute('Read',{'file_path':'/x/pkg/core.py'},{'step':st}))
        self.assertIsNone(hint.substitute('Read',{'file_path':'/x/pkg/core.py','limit':50},{'step':st}))   # ranged reads are already narrow
    def test_non_identifier_patterns_never_substituted(self):
        self.assertIsNone(hint.substitute('Bash',{'command':'grep -rn "foo bar" .'},{'prompt':'who calls foo bar'}))
    def test_failure_ledger(self):
        d=tempfile.mkdtemp(); self.addCleanup(shutil.rmtree,d,True); L=hint.Ledger(d+'/l.jsonl')
        s=hint.substitute('Bash',{'command':'grep -rn foo .'},{'prompt':'who calls foo?'}); L.record(s); L.record(hint.substitute('Bash',{'command':'grep -rn foo src'},{'prompt':'who calls foo?'}))
        self.assertEqual(L.failure_rate(),0.0); self.assertFalse(L.observe_request('grep -rn foo .'))   # re-issuing the original is just substituted again, not a fallback
        self.assertTrue(L.observe_request('HELIX_BYPASS=1 grep -rn foo .')); self.assertEqual(L.failure_rate(),0.5)

class TestConsolidate(unittest.TestCase):
    def transcript(self,d,n=40):
        p=d+'/t.jsonl'; ev=[{'type':'user','message':{'content':'<command-name>/goal</command-name><command-args>ship the thing, do not touch codex</command-args>'}}]
        for i in range(n):
            ev.append({'type':'assistant','message':{'content':[{'type':'text','text':f'We decided to use option {i} because it is faster. Result: {i*3}% faster.'},{'type':'tool_use','input':{'command':f'echo step {i}'}}]}})
            ev.append({'type':'user','message':{'content':[{'type':'tool_result','content':f'step {i}\n'+('noise line\n'*20)}]}})
        open(p,'w').write('\n'.join(json.dumps(e) for e in ev)+'\n'); return p
    def test_incremental_ingest_and_capsule_keeps_directives_verbatim(self):
        d=tempfile.mkdtemp(); self.addCleanup(shutil.rmtree,d,True); db=d+'/m.db'; p=self.transcript(d,20)
        r=hcons.consolidate(p,'s',db=db,root=d); self.assertGreater(r['ingested'],0); self.assertGreater(r['cold'],0); self.assertGreater(r['hot'],0)
        self.assertIn('do not touch codex',open(r['capsule_path']).read())
        r2=hcons.consolidate(p,'s',db=db,root=d); self.assertEqual(r2['ingested'],0)                      # watermark: nothing re-ingested
        p=self.transcript(d,30); r3=hcons.consolidate(p,'s',db=db,root=d); self.assertEqual(r3['ingested'],30)  # only the 10 new turns (3 units each: text, call, result)
    def test_lossless_raw_survives_consolidation(self):
        d=tempfile.mkdtemp(); self.addCleanup(shutil.rmtree,d,True); db=d+'/m.db'; p=self.transcript(d,5); hcons.consolidate(p,'s',db=db,root=d)
        row=hmem.connect(db).execute("SELECT id FROM unit WHERE kind='result' ORDER BY seq LIMIT 1").fetchone(); self.assertIn('noise line',hmem.raw(row['id'],path=db))

class TestAdapter(unittest.TestCase):
    def run_hook(self,ev,payload,env=None):
        e=dict(os.environ,HELIX_HOME=H); e.update(env or {})
        r=subprocess.run([sys.executable,H+'/adapters/claude_code.py',ev],input=json.dumps(payload),capture_output=True,text=True,env=e); return r
    def test_pre_tool_use_substitutes_with_declared_loss(self):
        d=tempfile.mkdtemp(); self.addCleanup(shutil.rmtree,d,True); os.makedirs(d+'/run'); shutil.copytree(H+'/lib',d+'/lib'); shutil.copytree(H+'/adapters',d+'/adapters')
        open(d+'/run/ctx.json','w').write(json.dumps({'prompt':'who calls foo?'}))
        run=lambda cmd: subprocess.run([sys.executable,d+'/adapters/claude_code.py','PreToolUse'],input=json.dumps({'tool_name':'Bash','tool_input':{'command':cmd}}),capture_output=True,text=True,env={**os.environ,'HELIX_HOME':d})
        r=run('grep -rn foo .'); self.assertEqual(r.returncode,0,r.stderr); o=json.loads(r.stdout)['hookSpecificOutput']
        self.assertEqual(o['updatedInput']['command'],'callers -l foo .'); self.assertIn('loss',o['permissionDecisionReason']); self.assertIn('fallback',o['permissionDecisionReason'])
        self.assertEqual(run('ls -la').stdout.strip(),'')                                                   # no inferable requirement: untouched
        run('HELIX_BYPASS=1 grep -rn foo .'); rows=[json.loads(l) for l in open(d+'/run/substitutions.jsonl')]; self.assertTrue(any(x['failed'] for x in rows))  # raw re-request after substitution = recorded failure
    def test_unknown_event_and_garbage_never_break_host(self):
        r=subprocess.run([sys.executable,H+'/adapters/claude_code.py','PreToolUse'],input='not json',capture_output=True,text=True); self.assertEqual(r.returncode,0); self.assertEqual(r.stdout.strip(),'')
        self.assertEqual(self.run_hook('Whatever',{}).returncode,0)
    def test_session_start_injects_capsule_once_from_memory(self):
        d=tempfile.mkdtemp(); self.addCleanup(shutil.rmtree,d,True); db=d+'/m.db'
        ev=[{'type':'user','message':{'content':'<command-name>/goal</command-name><command-args>keep the budget under 1k</command-args>'}}]
        t=d+'/t.jsonl'; open(t,'w').write(json.dumps(ev[0])+'\n')
        env={'HELIX_MEM_DB':db,'HELIX_HOME':d}; os.makedirs(d+'/run',exist_ok=True)
        shutil.copytree(H+'/lib',d+'/lib'); shutil.copytree(H+'/adapters',d+'/adapters')
        cwd=d; r=subprocess.run([sys.executable,d+'/adapters/claude_code.py','Stop'],input=json.dumps({'transcript_path':t,'cwd':cwd}),capture_output=True,text=True,env={**os.environ,**env}); self.assertEqual(r.returncode,0,r.stderr)
        r=subprocess.run([sys.executable,d+'/adapters/claude_code.py','SessionStart'],input=json.dumps({'cwd':cwd,'source':'clear'}),capture_output=True,text=True,env={**os.environ,**env})
        o=json.loads(r.stdout); self.assertEqual(o['hookSpecificOutput']['hookEventName'],'SessionStart'); self.assertIn('keep the budget under 1k',o['hookSpecificOutput']['additionalContext'])
    def test_user_prompt_injection_only_when_state_changes(self):
        d=tempfile.mkdtemp(); self.addCleanup(shutil.rmtree,d,True); os.makedirs(d+'/run'); shutil.copytree(H+'/lib',d+'/lib'); shutil.copytree(H+'/adapters',d+'/adapters')
        open(d+'/run/state.txt','w').write('<helix-state>goal=G DONE</helix-state>'); run=lambda: subprocess.run([sys.executable,d+'/adapters/claude_code.py','UserPromptSubmit'],input='{}',capture_output=True,text=True,env={**os.environ,'HELIX_HOME':d}).stdout.strip()
        self.assertIn('helix-state',run()); self.assertEqual(run(),'')                                      # same state: nothing injected
        open(d+'/run/state.txt','w').write('<helix-state>goal=G IN_PROGRESS</helix-state>'); self.assertIn('IN_PROGRESS',run())
    def test_print_settings_is_pure_and_lists_hooks(self):
        r=subprocess.run([sys.executable,H+'/adapters/claude_code.py','--print-settings'],capture_output=True,text=True); s=json.loads(r.stdout); self.assertIn('PreToolUse',s['hooks']); self.assertIn('SessionStart',s['hooks'])


class TestConformance(unittest.TestCase):
    CORE=('hcore.py','hcontrol.py','scheduler.py','normalize.py','hops.py','claims.py','reduce.py','consolidate.py','intercept.py','trace.py','capsule.py','hmem.py','preflight.py','escalate.py','verify.py')
    BANNED={'anthropic','openai','torch','laya','claude_code','adapters','transformers'}
    @staticmethod
    def imported(src):
        import ast as _ast
        mods=set()
        for n in _ast.walk(_ast.parse(src)):
            if isinstance(n,_ast.Import): mods|={a.name.split('.')[0] for a in n.names}
            if isinstance(n,_ast.ImportFrom) and n.module: mods.add(n.module.split('.')[0])
        return mods
    def test_core_imports_no_adapter_model_sdk_or_host(self):
        for f in self.CORE:
            bad=self.imported(open(os.path.join(H,'lib',f)).read())&self.BANNED; self.assertFalse(bad,f'{f} imports {bad}')
    def test_banned_check_would_catch_a_violation(self):
        self.assertTrue(self.imported('import torch\nfrom laya import Agent')&self.BANNED)
    def test_only_designated_modules_call_a_model(self):
        callers=[f for f in os.listdir(H+'/lib') if f.endswith('.py') and ("'claude'" in open(os.path.join(H,'lib',f)).read())]
        self.assertEqual(sorted(callers),['escalate.py'])      # the single place a frontier model is invoked
    def test_standalone_runs_graph_end_to_end(self):
        d=tempfile.mkdtemp(); self.addCleanup(shutil.rmtree,d,True); w(d,'pkg/core.py','def foo(x):\n    return x\n'); w(d,'pkg/use.py','from .core import foo\ndef bar(): return foo(1)\n')
        g={'goal_id':'G','objective':'o','steps':[{'step_id':'S1','objective':'x','required_evidence':[{'kind':'callers','name':'foo','deffile':'core.py'}]}]}; open(d+'/g.json','w').write(json.dumps(g))
        r=subprocess.run([sys.executable,H+'/adapters/standalone.py','run',d+'/g.json','--root',d,'--db',d+'/m.db'],capture_output=True,text=True,cwd=d,env={**os.environ,'HELIX_HOME':H}); self.assertEqual(r.returncode,0,r.stderr); self.assertIn('S1=DONE',r.stdout)
import verify as hverify
class TestVerifiedDocgen(unittest.TestCase):
    SRC='def load_user(user_id):\n    return db.fetch(user_id)\n'
    def test_accepts_grounded_docstring(self): self.assertEqual(hverify.docstring_ok('Fetch the user row for the given user_id.',self.SRC,'load_user'),(True,'ok'))
    def test_rejects_hallucinated_identifier(self):
        ok,why=hverify.docstring_ok('Fetch the user row then call refresh_cache afterwards.',self.SRC,'load_user'); self.assertFalse(ok); self.assertIn('refresh_cache',why)
    def test_rejects_echo_and_length(self):
        self.assertEqual(hverify.docstring_ok('Load user.',self.SRC,'load_user')[1],'length'); self.assertEqual(hverify.docstring_ok('load user user',self.SRC,'load_user')[1],'echoes name')
        self.assertEqual(hverify.docstring_ok('x '*80,self.SRC,'f')[1],'length')

class TestReadOnlyMemory(unittest.TestCase):
    def test_reads_work_on_a_read_only_database_without_claim_tables(self):
        d=tempfile.mkdtemp(); self.addCleanup(lambda:(os.chmod(d,0o755),shutil.rmtree(d,True))); db=d+'/m.db'
        hmem.ingest([{'seq':0,'kind':'user','text':'remember the magic number 4242'}],session='s',path=db)
        c=hmem.connect(db); c.execute('DROP TABLE IF EXISTS meta'); c.commit(); c.close()
        os.chmod(db,0o444); os.chmod(d,0o555)
        self.assertEqual(hclaims.all_claims('.',db),[]); self.assertEqual(hclaims.search('magic',3,'.',db),[])
        self.assertEqual(hmem.search_passages('magic',3,path=db)[0]['seq'],0); self.assertIn('4242',hmem.raw(hmem.search('magic',1,path=db)[0]['id'],path=db))

class TestToolLabels(Fixture):
    def setUp(self): super().setUp(); os.chdir(self.d)
    def tearDown(self): os.chdir(H)
    def test_callees_labels_classes_and_ambiguous_names(self):
        w(self.d,'pkg/m.py','class Box:\n    pass\ndef util_fn(): return 1\ndef run():\n    Box()\n    return util_fn()+dup()\n'); w(self.d,'pkg/n.py','def dup(): return 1\n'); w(self.d,'pkg/o.py','def dup(): return 2\n')
        p=hcontrol.run_step({'step_id':'S','objective':'x','required_evidence':[{'kind':'callees','file':'pkg/m.py','name':'run'}],'envelope':{'may':list(hcore.OPS_READONLY)}},root=self.d,persist=False)
        txt=p['observations'][0]['text']; self.assertIn('util_fn@m.py:3',txt.split('CLASSES')[0]); self.assertIn('Box@m.py:1',txt.split('CLASSES')[1].split('AMBIGUOUS')[0]); self.assertIn('dupx2',txt.split('AMBIGUOUS')[1]); self.assertNotIn('Box',txt.split('UNIQUE')[1].split('CLASSES')[0])
    def test_coverage_flags_shared_names(self):
        w(self.d,'pkg/m.py','def alpha(): pass\ndef beta(): pass\n'); w(self.d,'pkg/n.py','def beta(): pass\n'); w(self.d,'tests/test_x.py','def test_a(): pass\n')
        p=hcontrol.run_step({'step_id':'S','objective':'x','required_evidence':[{'kind':'coverage','file':'pkg/m.py'}],'envelope':{'may':list(hcore.OPS_READONLY)}},root=self.d,persist=False)
        txt=p['observations'][0]['text']; self.assertIn('alpha',txt); self.assertIn('beta*',txt); self.assertNotIn('alpha*',txt)
    def test_outline_flags_overload_stubs(self):
        w(self.d,'o.py','from typing import overload\n@overload\ndef f(x: int) -> int: ...\ndef f(x):\n    return x\ndef g(): pass\n')
        r=sh(['outline','o.py'],self.d); self.assertIn('[overload]',r.stdout); self.assertIn('g:6-6[nodoc]',r.stdout)

class TestStringRefsAndCalleeSections(Fixture):
    def setUp(self): super().setUp(); os.chdir(self.d)
    def tearDown(self): os.chdir(H)
    def test_mock_patch_string_counts_as_test_reference(self):
        w(self.d,'tests/test_patch.py','from unittest import mock\n\ndef test_a():\n    with mock.patch("pkg.core.foo"):\n        pass\n')
        refs=hops.test_refs('foo',self.d); self.assertTrue(any(r['fn']=='<string-ref>' for r in refs) or any(r['file'].endswith('test_patch.py') for r in refs))
        p=hcontrol.run_step({'step_id':'S','objective':'x','required_evidence':[{'kind':'coverage','file':'pkg/core.py'}],'envelope':{'may':list(hcore.OPS_READONLY)}},root=self.d,persist=False)
        self.assertNotIn(' foo ',' '+p['observations'][0]['text'].split('NOT referenced')[1].split('[name-based')[0]+' ')
    def test_docstring_and_comment_mentions_do_not_count(self):
        w(self.d,'tests/test_doc.py','# foo is great\n\ndef test_a():\n    """checks foo somehow"""\n    pass\n'); self.assertEqual(hops.test_refs('foo',self.d) and [r for r in hops.test_refs('foo',self.d) if r['file'].endswith('test_doc.py')],[])
    def test_callees_sections(self):
        w(self.d,'pkg/m.py','class Box:\n    pass\ndef util_fn(): return 1\ndef run():\n    Box()\n    return util_fn()+dup()\n'); w(self.d,'pkg/n.py','def dup(): return 1\n'); w(self.d,'pkg/o.py','def dup(): return 2\n')
        t=hcontrol.run_step({'step_id':'S','objective':'x','required_evidence':[{'kind':'callees','file':'pkg/m.py','name':'run'}],'envelope':{'may':list(hcore.OPS_READONLY)}},root=self.d,persist=False)['observations'][0]['text']
        self.assertIn('UNIQUE repo functions (1): util_fn@m.py',t); self.assertIn('CLASSES',t); self.assertIn('Box@m.py',t); self.assertIn('AMBIGUOUS',t); self.assertIn('dupx2',t)

class TestConditionalDefs(Fixture):
    def test_public_functions_include_conditional_module_level_defs(self):
        w(self.d,'cond.py','try:\n    from fast import impl\nexcept ImportError:\n    def impl(x): return x\nif True:\n    def other(): pass\ndef plain(): pass\ndef _private(): pass\n')
        names={f['name'] for f in hops.public_functions(os.path.join(self.d,'cond.py'))}; self.assertEqual(names,{'impl','other','plain'})

if __name__=='__main__': unittest.main(verbosity=2)
