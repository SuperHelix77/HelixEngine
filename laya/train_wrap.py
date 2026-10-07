"""laya-train with periodic MPS cache release (variable-length batches fragment the MPS allocator and OOM long runs)."""
import sys,gc,torch
import laya.train as T
_orig=T._forward; _n=[0]
def _fwd(*a,**k):
    _n[0]+=1
    if _n[0]%20==0:
        gc.collect(); torch.mps.empty_cache()
    if _n[0]%200==0: print(f"[mem] call {_n[0]} allocated {torch.mps.current_allocated_memory()/2**30:.1f} GiB driver {torch.mps.driver_allocated_memory()/2**30:.1f} GiB",file=sys.stderr,flush=True)
    return _orig(*a,**k)
T._forward=_fwd
from laya.train_cli import main
sys.exit(main())
