import sys,os,csv,json,time,glob
os.environ['USE_TF']='0'; os.environ['HF_HUB_OFFLINE']='1'
from laya import Router
ck=sys.argv[1]; thr=[0.0,0.7,0.9,0.95]
qf=glob.glob(ck+'/*question*.json')+glob.glob(ck+'/questions*.json')
Q=json.load(open(qf[0])) if qf else None
r=Router(models={'rt':ck}) if False else None
from laya import Agent
a=Agent(ck)
if Q is None: raise SystemExit('no question schema found: '+str(os.listdir(ck)))
Q=Q.get('questions',Q)
def pred(t):
    x=a.predict(t,Q); k=list(x['answers'])[0]; v=x['answers'][k]; return v['choice'],v['answer_confidence']
for name in ['test_newphrase','test_newentity','test_both']:
    rows=list(csv.DictReader(open(f'{name}.csv'))); t=time.time(); P=[pred(r['text']) for r in rows]; dt=(time.time()-t)/len(rows)
    out=[]
    for th in thr:
        ok=fr=miss=wrongcmd=0
        for r,(c,cf) in zip(rows,P):
            p=c if (c!='escalate' and cf>=th) else 'escalate'; e=r['label']
            ok+=p==e; fr+=(p!='escalate' and e=='escalate'); miss+=(p=='escalate' and e!='escalate'); wrongcmd+=(p!='escalate' and e!='escalate' and p!=e)
        out.append(f'thr{th}: acc {100*ok/len(rows):.1f}% false-route {fr} missed {miss} wrong-cmd {wrongcmd}')
    print(name,len(rows),f'{dt*1000:.0f}ms/dec'); [print('  ',o) for o in out]
# hand-written 27
sys.path.insert(0,'.')
src=open(os.path.join(os.environ.get('HELIX_HOME',os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),'bench/routetest.py')).read().split("ok=fr=miss=0")[0]
ns={'__file__':os.path.join(os.environ.get('HELIX_HOME',os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),'bench','routetest.py')}; exec(src.replace('import route','route=None').replace('cwd=sys.argv[1]; ','cwd=\'\';'),ns)
rows=[(p,e or 'escalate') for p,e in ns['CASES']]; P=[pred(p) for p,_ in rows]
for th in thr:
    ok=fr=miss=0
    for (p,e),(c,cf) in zip(rows,P):
        pr=c if (c!='escalate' and cf>=th) else 'escalate'; ok+=pr==e; fr+=(pr!='escalate' and e=='escalate'); miss+=(pr=='escalate' and e!='escalate')
    print(f'hand27 thr{th}: acc {ok}/{len(rows)} false-route {fr} missed {miss}')
for (p,e),(c,cf) in zip(rows,P):
    if c!=e: print('   X',e,'->',c,round(cf,2),'|',p[:70])
