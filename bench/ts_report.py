"""ts_report.py: token-saving metrics report (markdown + JSON). Savings are computed over TASKS (resampled for CIs), correctness is the blind-judge verdict."""
import os,sys,json,glob,random,statistics as st,collections
H=os.environ.get('HELIX_HOME',os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); RES=H+f"/bench/ts_results{os.environ.get('TS_SET','')}{os.environ.get('TS_OUT','')}"
random.seed(1)
CATS=['input','cache_write','cache_read','output']
def load():
    R=collections.defaultdict(lambda:collections.defaultdict(list))
    for f in sorted(glob.glob(RES+'/*__*__*.json')):
        r=json.load(open(f))
        if 'err' in r or 'judged' not in r: continue
        r['correct']=(r['judged']=='CORRECT'); r['in_total']=r['input']+r['cache_write']+r['cache_read']; r['all']=r['in_total']+r['output']
        r['weighted']=r['input']+1.25*r['cache_write']+0.1*r['cache_read']+5*r['output']    # relative to 1 fresh input token (Sonnet-class price ratios)
        R[r['cfg']][r['id']].append(r)
    return R
def per_task(R,cfg,key): return {t:st.mean(x[key] for x in rs) for t,rs in R[cfg].items()}
def agg_savings(base,helix,tasks):
    b=sum(base[t] for t in tasks); h=sum(helix[t] for t in tasks); return 1-h/b if b else float('nan')
def boot(base,helix,tasks,n=2000):
    xs=[]
    for _ in range(n):
        s=[random.choice(tasks) for _ in tasks]; xs.append(agg_savings(base,helix,s))
    xs.sort(); return xs[int(.025*n)],xs[int(.975*n)]
def report(base_cfg='A',cfgs=('L1','L2')):
    R=load(); out={'n_tasks':{},'configs':{}}; lines=[]
    for c in (base_cfg,)+tuple(cfgs):
        if c in R: out['n_tasks'][c]=len(R[c])
    common=sorted(set.intersection(*[set(R[c]) for c in (base_cfg,)+tuple(cfgs) if c in R]))
    lines.append(f"# Helix token-saving metrics\n\nTasks: {len(common)} (4 repos x 7 families, ground truth by independent textual method cross-checked with AST). Reps: "+', '.join(f"{c} n={round(st.mean(len(R[c][t]) for t in common),1)}" for c in (base_cfg,)+tuple(cfgs) if c in R)+". Correctness: blind LLM judge. CI: 95% bootstrap over tasks.\n")
    metrics=[('input','fresh input'),('cache_write','cache write'),('cache_read','cache read'),('in_total','input+cache (all)'),('output','output'),('all','total tokens'),('weighted','price-weighted units'),('cost_usd','list cost USD'),('turns','frontier turns'),('wall_s','wall-clock s')]
    base={m:per_task(R,base_cfg,m) for m,_ in metrics}
    for c in cfgs:
        if c not in R: continue
        h={m:per_task(R,c,m) for m,_ in metrics}; row={}
        lines.append(f"\n## {c} vs {base_cfg}\n\n| metric | {base_cfg} (sum over tasks) | {c} | savings | 95% CI | median per-task |\n|---|---:|---:|---:|---|---:|")
        for m,lab in metrics:
            lo,hi=boot(base[m],h[m],common); sv=agg_savings(base[m],h[m],common); med=st.median(1-h[m][t]/base[m][t] for t in common if base[m][t])
            row[m]={'baseline':sum(base[m][t] for t in common),'helix':sum(h[m][t] for t in common),'savings':sv,'ci':[lo,hi],'median_task':med}
            f=lambda v:f"{v:,.2f}" if m in('cost_usd',) else f"{v:,.0f}"
            lines.append(f"| {lab} | {f(row[m]['baseline'])} | {f(row[m]['helix'])} | **{100*sv:.1f}%** | {100*lo:.1f}..{100*hi:.1f}% | {100*med:.1f}% |")
        # correctness + efficiency
        cb=sum(sum(x['correct'] for x in R[base_cfg][t])/len(R[base_cfg][t]) for t in common)/len(common); ch=sum(sum(x['correct'] for x in R[c][t])/len(R[c][t]) for t in common)/len(common)
        eb=len(common)*cb/sum(base['all'][t] for t in common)*1e6; eh=len(common)*ch/sum(h['all'][t] for t in common)*1e6
        row['correct']={'baseline':cb,'helix':ch}; row['correct_per_million_tokens']={'baseline':eb,'helix':eh}
        lines.append(f"\nCorrectness: {base_cfg} {100*cb:.1f}% vs {c} {100*ch:.1f}%. Correct answers per million tokens: {eb:.1f} vs {eh:.1f} (**{eh/eb:.0f}x**).")
        # by family / repo
        for dim,keyf in (('family',lambda t:R[c][t][0]['family']),('repo',lambda t:R[c][t][0]['repo'])):
            lines.append(f"\n| {dim} | tasks | in+cache savings | output savings | turns {base_cfg}->{c} | correct {base_cfg}/{c} |\n|---|---:|---:|---:|---|---|"); groups=collections.defaultdict(list)
            for t in common: groups[keyf(t)].append(t)
            for g,ts in sorted(groups.items()):
                cb_=sum(sum(x['correct'] for x in R[base_cfg][t])/len(R[base_cfg][t]) for t in ts)/len(ts); ch_=sum(sum(x['correct'] for x in R[c][t])/len(R[c][t]) for t in ts)/len(ts)
                lines.append(f"| {g} | {len(ts)} | {100*agg_savings(base['in_total'],h['in_total'],ts):.1f}% | {100*agg_savings(base['output'],h['output'],ts):.1f}% | {st.mean(base['turns'][t] for t in ts):.1f} -> {st.mean(h['turns'][t] for t in ts):.1f} | {100*cb_:.0f}% / {100*ch_:.0f}% |")
        out['configs'][c]=row
    open(H+f"/bench/TOKEN_METRICS{os.environ.get('TS_SET','')}.md",'w').write('\n'.join(lines)+'\n'); json.dump(out,open(H+f"/bench/token_metrics{os.environ.get('TS_SET','')}.json",'w'),indent=1); print('\n'.join(lines))
if __name__=='__main__': report()
