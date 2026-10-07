#!/usr/bin/env python3
"""Minimal MCP stdio server: one shell tool, rtk-rewritten, output-capped. Tiny schema = tiny tokens."""
import sys, json, subprocess, re, os
RTK = "/opt/homebrew/bin/rtk"
HELIX_HOME = os.environ.get("HELIX_HOME", os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HELIX_HOME, "lib"))
try:
    import reduce as hreduce
except Exception:
    hreduce = None
os.environ["PATH"] = os.path.join(HELIX_HOME, "bin") + ":" + os.environ["PATH"]
CAP = int(os.environ.get("SH_CAP", "5000"))
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

def run(cmd):
    cmd0 = cmd
    global PREVIEW
    PREVIEW = None
    if cmd.startswith("raw "): return raw(cmd[4:])
    try:
        r = subprocess.run([RTK, "rewrite", cmd], capture_output=True, text=True, timeout=5)
        if r.returncode in (0, 3) and r.stdout.strip():
            cmd = r.stdout.strip()
            m = re.fullmatch(r"rtk read (\S+)", cmd)
            if m and os.environ.get("CL_READ_POLICY", "preview") == "preview":
                try:
                    if os.path.getsize(m.group(1)) > int(os.environ.get("CL_PREVIEW_BYTES", "9000")):
                        cmd = f"rtk read -m 70 {m.group(1)}"; PREVIEW = m.group(1)
                except OSError: pass
    except Exception:
        pass
    argv = ["/bin/zsh", "-c", cmd]
    sb = os.environ.get("SH_SANDBOX_DIR")
    if sb:  # bench mode: no network, writes only under sb
        prof = ('(version 1)(allow default)(deny network*)(deny file-write*)'
                '(allow network-outbound (remote ip "localhost:11500"))'
                '(allow file-write* (subpath "%s") (literal "/dev/null") (literal "/dev/tty") (subpath "/private/var/folders"))' % os.path.realpath(sb))
        argv = ["/usr/bin/sandbox-exec", "-p", prof] + argv
    elif os.environ.get("SH_REQUIRE_SANDBOX"):
        return "refused: sandbox required"
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=120)
        out = (p.stdout or "") + (p.stderr or "")
        rc = p.returncode
    except subprocess.TimeoutExpired:
        out, rc = "timeout", 124
    out = ANSI.sub("", out)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return finish(cmd0, out, rc)

CALLS = []   # raw outputs by call number (lossless, session-local)
SEEN = {}    # (cmd, output hash) -> call number
ERR = re.compile(r"error|fail|exception|traceback|assert|panic|fatal|denied|warn", re.I)

def project(out, cap):
    """Deterministic semantic projection: collapse repeats, keep head, error lines, tail."""
    lines = out.split("\n"); res = []; i = 0
    while i < len(lines):
        j = i
        while j + 1 < len(lines) and lines[j + 1] == lines[i]: j += 1
        res.append(lines[i] + (f"  [x{j-i+1}]" if j > i else "")); i = j + 1
    txt = "\n".join(res)
    if len(txt) <= cap: return txt
    h, e, t = cap * 4 // 10, cap * 3 // 10, cap * 3 // 10
    head = []; n = 0
    for l in res:
        if n + len(l) > h: break
        head.append(l); n += len(l) + 1
    rest = res[len(head):]
    errs = []; n = 0
    for l in rest:
        if ERR.search(l) and n + len(l) <= e: errs.append(l[:200]); n += len(l) + 1
    tail = []; n = 0
    for l in reversed(rest):
        if n + len(l) > t: break
        tail.append(l); n += len(l) + 1
    tail.reverse()
    return "\n".join(head + ["..."] + errs + ["..."] + tail)

PREVIEW = None
def finish(cmd, out, rc):
    n = len(CALLS) + 1; CALLS.append(out)
    rd = os.environ.get("CL_RUN_DIR")
    if rd:
        try:
            os.makedirs(rd, exist_ok=True); open(os.path.join(rd, f"{n}.txt"), "w").write(out)
        except Exception: pass
    key = (cmd, hash(out))
    if key in SEEN and out:
        return f"=#{SEEN[key]} (unchanged)"
    SEEN[key] = n
    body = out or "ok"
    rec = hreduce.reduce(out, cmd) if (hreduce and out and os.environ.get("HELIX_SEMANTIC_REDUCE", "1") == "1") else None
    if rec is not None:   # typed receipt replaces bytes; raw N stays exact
        return rec.render(f"raw {n}") + (f"\n[rc={rc}]" if rc else "")
    if PREVIEW: body += f"\n[preview; sym {PREVIEW} NAME | full {PREVIEW}]"
    if len(out) > CAP:
        body = project(out, CAP) + f"\n[#{n}: {out.count(chr(10))+1} lines; raw {n} A-B for exact]"
    return body + (f"\n[rc={rc}]" if rc else "")

def raw(arg):
    m = re.fullmatch(r"\s*(\d+)(?:\s+(\d+)-(\d+))?\s*", arg)
    if not m or not (1 <= int(m.group(1)) <= len(CALLS)): return "bad handle"
    ls = CALLS[int(m.group(1)) - 1].split("\n")
    a, b = (int(m.group(2)), int(m.group(3))) if m.group(2) else (1, len(ls))
    return "\n".join(f"{i}:{l}" for i, l in enumerate(ls[a-1:b], a))[:CAP * 2]

def send(o):
    sys.stdout.write(json.dumps(o, separators=(",", ":")) + "\n"); sys.stdout.flush()

for line in sys.stdin:
    try: m = json.loads(line)
    except Exception: continue
    i, meth = m.get("id"), m.get("method")
    if meth == "initialize":
        send({"jsonrpc": "2.0", "id": i, "result": {"protocolVersion": m["params"].get("protocolVersion", "2024-11-05"),
              "capabilities": {"tools": {}}, "serverInfo": {"name": "s", "version": "1"}}})
    elif meth == "tools/list":
        send({"jsonrpc": "2.0", "id": i, "result": {"tools": [{"name": "x", "description": "shell",
              "inputSchema": {"type": "object", "properties": {"c": {"type": "string"}}, "required": ["c"]}}]}})
    elif meth == "tools/call":
        c = (m["params"].get("arguments") or {}).get("c", "")
        send({"jsonrpc": "2.0", "id": i, "result": {"content": [{"type": "text", "text": run(c)}]}})
    elif i is not None:
        send({"jsonrpc": "2.0", "id": i, "result": {}})
