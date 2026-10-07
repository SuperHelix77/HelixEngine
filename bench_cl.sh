#!/bin/zsh
# bench-only: sandboxed + pre-approved lean claude. cwd = sandbox dir. CL_RUN_DIR keeps raw call outputs for @N expansion.
D=$PWD
H=${HELIX_HOME:-${0:A:h}}
PY=${HELIX_PYTHON:-/usr/bin/python3}; [ -x "$PY" ] || PY=$(command -v python3)
$H/lmup.sh
RD=${CL_RUN_DIR:-/tmp/clrun_$$}
cat > /tmp/.cl_bench_mcp_$$.json <<J
{"mcpServers":{"s":{"command":"$PY","args":["$H/sh_mcp.py"],"env":{"SH_SANDBOX_DIR":"$D","SH_REQUIRE_SANDBOX":"1","CL_RUN_DIR":"$RD"}}}}
J
claude --setting-sources project --settings "$H/settings.json" --disable-slash-commands --strict-mcp-config \
  --mcp-config /tmp/.cl_bench_mcp_$$.json --tools "" --system-prompt "$(cat ${CL_PROMPT:-$H/prompt.txt})" \
  --model "${CL_MODEL:-sonnet}" --exclude-dynamic-system-prompt-sections --effort low --allowedTools mcp__s__x "$@"
rm -f /tmp/.cl_bench_mcp_$$.json
