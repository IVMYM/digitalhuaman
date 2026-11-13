#!/bin/zsh
set -e
cd "$(dirname "$0")"
python3 -m venv .venv-local 2>/dev/null || true
source .venv-local/bin/activate
pip install -r local-requirements.txt
export LIVETALKING_LOCAL_URL="${LIVETALKING_LOCAL_URL:-http://127.0.0.1:8010}"
uvicorn local_avatar:app --host 0.0.0.0 --port "${LOCAL_AVATAR_PORT:-8090}"

