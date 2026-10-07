#!/usr/bin/env python3
"""helix compose [--terse ultra|full|lite|off] [--handle]  -> static system prompt (stdout). Built once per launch; byte-stable => prefix-cache friendly.
Terse style lives ONLY here (never as a per-turn hook or skill)."""
import sys,os,hashlib
H=os.environ.get('HELIX_HOME',os.path.dirname(os.path.abspath(__file__)))
def rd(p):
    try: return open(os.path.join(H,p)).read().strip()
    except FileNotFoundError: return ''
def compose(level='ultra',handle=False):
    if level not in('ultra','full','lite','off'): level='ultra'
    parts=[rd(f'terse/{level}.txt'),rd('prompt.d/00-core.txt')]+([rd('prompt.d/90-handle.txt')] if handle else [])
    return ' '.join(p for p in parts if p)
if __name__=='__main__':
    a=sys.argv[1:]; lvl=a[a.index('--terse')+1] if '--terse' in a else os.environ.get('HELIX_TERSE','ultra')
    p=compose(lvl,'--handle' in a)
    if '--hash' in a: print(hashlib.sha256(p.encode()).hexdigest()[:12])
    else: print(p)
