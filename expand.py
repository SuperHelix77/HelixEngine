#!/usr/bin/env python3
# expand.py RUN_DIR : stdin text/JSON(result) -> replace "@N" / "@N A-B" with exact stored tool output
import sys,re,json,os
rd=sys.argv[1]
def sub(t):
    def f(m):
        p=os.path.join(rd,m.group(1)+'.txt')
        if not os.path.exists(p): return m.group(0)
        ls=open(p).read().split('\n')
        if m.group(2): a,b=int(m.group(2)),int(m.group(3)); ls=ls[a-1:b]
        return '\n'.join(ls)
    return re.sub(r'@(\d+)(?:\s+(\d+)-(\d+))?',f,t)
d=sys.stdin.read()
try:
    j=json.loads(d); j['result']=sub(j.get('result') or ''); print(json.dumps(j))
except Exception: print(sub(d),end='')
