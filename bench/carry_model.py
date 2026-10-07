"""carry_model.py: replay a real transcript and total the context tokens carried across turns under three policies. MODELED (assumptions printed), real token sizes."""
import sys,os,json,tiktoken
H=os.environ.get('HELIX_HOME',os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); sys.path.insert(0,H+'/lib'); import hmem
enc=tiktoken.get_encoding('cl100k_base'); T=lambda s:len(enc.encode(s))
if len(sys.argv)<2: sys.exit('usage: carry_model.py TRANSCRIPT.jsonl   (a Claude Code transcript from ~/.claude/projects/...)')
P=sys.argv[1]
U=hmem.units_from_transcript(P); sz=[T(u['text'][:1500] if u['kind']=='result' else u['text']) for u in U]
turns=[i for i,u in enumerate(U) if u['kind']=='assistant' or u['kind']=='call']      # a model step happens at each assistant/call unit
W=40000; SUMMARY=2200; CAPSULE=1000; HOT=12; Q_PER_20=3; Q_COST=1200
# B state machine
def policy_B():
    carried=0; start=0; comp=0; n=0; tot=0; summ=0
    for t in turns:
        cur=summ+sum(sz[start:t])
        if cur>W: comp+=cur+SUMMARY; n+=1; summ=SUMMARY; start=t; cur=summ
        tot+=cur
    return tot,comp,n
def policy_C():
    tot=0; q=0
    for k,t in enumerate(turns):
        lo=max(0,t-HOT); tot+=CAPSULE+sum(sz[lo:t])
    q=(len(turns)/20)*Q_PER_20*Q_COST
    return tot,q
A=sum(sum(sz[:t]) for t in turns); Btot,Bcomp,Bn=policy_B(); Ctot,Cq=policy_C()
rows=[('A no compaction (history grows)',A,0),('B native compaction @40k window',Btot,Bcomp),('C Helix memory (capsule+12-unit window+queries)',Ctot,Cq)]
print(f'transcript units {len(U)}, model steps {len(turns)}, total history tokens {sum(sz)}')
print(f'assumptions: window {W}, summary {SUMMARY} tok (+ one full-context call per compaction), capsule {CAPSULE}, hot window {HOT} units, {Q_PER_20} memory lookups per 20 steps at {Q_COST} tok each')
print(f"{'policy':52}{'carried ctx tokens':>20}{'extra call tokens':>20}{'total':>12}{'vs A':>8}")
for n,c,e in rows: print(f"{n:52}{c:>20,}{int(e):>20,}{int(c+e):>12,}{100*(1-(c+e)/A):>7.1f}%")
print('compactions in B:',Bn)
json.dump({'steps':len(turns),'A':A,'B':{'carried':Btot,'compaction_calls':Bcomp,'n':Bn},'C':{'carried':Ctot,'queries':Cq}},open(H+'/bench/carry_model.json','w'),indent=1)
