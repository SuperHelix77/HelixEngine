"""Deterministic verification for local-model output (mechanical offload is only safe with a checker)."""
import re
def docstring_ok(doc,src,name):
    """-> (ok, reason). Rejects: too short/long, an echo of the function name, or concrete identifiers that do not occur in the code."""
    if len(doc.split())<3 or len(doc)>110: return False,'length'
    stop={'the','a','an','of','to','for','and','this','that','function','method','returns','return','does','is'}
    nw=set(re.findall(r'[a-z]+',name.lower().replace('_',' ')))|{w.rstrip('s') for w in re.findall(r'[a-z]+',name.lower().replace('_',' '))}
    content=[w for w in re.findall(r'[a-z]+',doc.lower()) if w not in stop]
    if content and all((w in nw or w.rstrip('s') in nw) for w in content): return False,'echoes name'
    idents=set(re.findall(r'\b[a-z]+_[a-z_0-9]+\b|\b[A-Z][a-z]+[A-Z]\w*\b',doc))
    unknown=sorted(i for i in idents if i not in src)
    if unknown: return False,'hallucinated identifier '+unknown[0]
    return True,'ok'
