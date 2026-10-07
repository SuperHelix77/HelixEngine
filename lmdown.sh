#!/bin/zsh
# stop ONLY the private local-LLM server on :11500 (never touches the shared ollama on :11434)
lsof -ti tcp:11500 -sTCP:LISTEN | xargs -r kill 2>/dev/null; echo stopped
