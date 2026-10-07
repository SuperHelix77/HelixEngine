import subprocess,json,sys,concurrent.futures as cf,re
LABELS={'callers':('who calls or uses a function, or where it is defined/used','{fn} {file} {dir}'),
'summ':('summarize or describe what a named file does','{file}'),
'ask':('answer a specific question about code behaviour in a named file/function (what happens when, defaults, errors raised, return values)','{file} {fn} {cond} {param}'),
'outline':('list the functions/classes/structure of a named file','{file}'),
'sym':('show the source code of one named function','{fn} {file}'),
'docgen':('add missing docstrings/documentation comments to a named file','{file}'),
'escalate':('ANYTHING ELSE a developer might say to a coding assistant: bug fixing, writing/refactoring/renaming/deleting code, running tests/commands, debugging, design questions, general knowledge, chit-chat, vague or follow-up replies (yes/ok/go ahead/continue), requests with no concrete file or function, multi-step requests that combine a lookup with a change','{file} {fn} {thing} {concept}')}
def gen(label,style,n):
    desc,ph=LABELS[label]
    extra=("Use UNUSUAL, indirect, verbose, slangy or typo-laden phrasing; vary sentence shape widely." if style=='test' else "Vary tone (terse, polite, casual, imperative, question), length and word choice widely.")
    p=f"Write {n} diverse, realistic messages a developer might send to a coding assistant that belong to this intent: {label} = {desc}.\nUse these placeholders where a concrete name belongs (only these): {ph}. Each message must contain the placeholders that make sense for the intent{' (escalate messages may contain none, or some)' if label=='escalate' else ' (at least one)'}.\n{extra}\nOutput ONLY a JSON array of {n} strings, no commentary."
    r=subprocess.run(['claude','-p',p,'--output-format','json','--no-session-persistence','--setting-sources','project','--tools','','--strict-mcp-config','--disable-slash-commands','--model','sonnet','--effort','low','--system-prompt','Output only valid JSON.'],capture_output=True,text=True,stdin=subprocess.DEVNULL,timeout=600)
    t=json.loads(r.stdout)['result']; m=re.search(r'\[.*\]',t,re.S); arr=json.loads(m.group(0))
    return label,style,[a for a in arr if isinstance(a,str)]
jobs=[(l,s,n) for l in LABELS for s,n in (('train',70),('test',25))]
with cf.ThreadPoolExecutor(7) as ex:
    for l,s,arr in ex.map(lambda a:gen(*a),jobs):
        json.dump(arr,open(f'tpl/{l}_{s}.json','w'),indent=0); print(l,s,len(arr),'|',arr[0][:70],'|',arr[-1][:70])
