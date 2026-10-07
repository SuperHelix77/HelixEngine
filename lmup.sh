#!/bin/zsh
# start private local-LLM server (port 11500) if down; separate from the shared ollama on 11434
curl -s -m1 http://127.0.0.1:11500/api/tags >/dev/null 2>&1 && exit 0
OLLAMA_HOST=127.0.0.1:11500 OLLAMA_KEEP_ALIVE=30m OLLAMA_NUM_PARALLEL=1 OLLAMA_CONTEXT_LENGTH=8192 nohup ollama serve >${HELIX_HOME:-${0:A:h}}/run/ollama.log 2>&1 &
for i in 1 2 3 4 5 6 7 8; do sleep 0.5; curl -s -m1 http://127.0.0.1:11500/api/tags >/dev/null 2>&1 && exit 0; done
