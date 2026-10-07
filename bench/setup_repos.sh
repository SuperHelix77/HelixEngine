#!/usr/bin/env bash
# Fetch the 4 benchmark repos into WORKDIR (default ./bench/work) in the layout bench/ts_tasks.py expects.
#   bench/setup_repos.sh [WORKDIR]
set -euo pipefail
W="${1:-$(cd "$(dirname "$0")" && pwd)/work}"; mkdir -p "$W"; cd "$W"; T="$(mktemp -d)"
# 1) HelixEngine v0.1.0 (this repo's legacy-v0.1.0 branch): package + tests + scripts
git clone -q --depth 1 --branch legacy-v0.1.0 https://github.com/SuperHelix77/HelixEngine.git "$T/he"
rm -rf helixengine; mkdir helixengine; cp -R "$T/he/helixengine" "$T/he/tests" "$T/he/scripts" helixengine/ 2>/dev/null || true; find helixengine -name __pycache__ -prune -exec rm -rf {} +
# 2) HelixContext: python files only, minus benchmarks/results
git clone -q --depth 1 https://github.com/SuperHelix77/HelixContext.git "$T/hc"
rm -rf helixcontext; mkdir helixcontext; (cd "$T/hc" && find . -name '*.py' -not -path './benchmarks/*' -not -path './results/*' | while read -r f; do mkdir -p "$W/helixcontext/$(dirname "$f")"; cp "$f" "$W/helixcontext/$f"; done)
# 3) click 8.5.0 and requests 2.34.2 source distributions (they ship their tests)
python3 -m pip download click==8.5.0 requests==2.34.2 --no-binary :all: --no-deps -q -d "$T/sd"
rm -rf click requests; tar xzf "$T/sd/click-8.5.0.tar.gz" -C "$T/sd"; tar xzf "$T/sd/requests-2.34.2.tar.gz" -C "$T/sd"; mv "$T/sd/click-8.5.0" click; mv "$T/sd/requests-2.34.2" requests
rm -rf "$T"; echo "repos ready in $W: $(ls "$W" | tr '\n' ' ')"
