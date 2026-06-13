#!/usr/bin/env bash
# Start the LiteLLM gateway. Works in three environments:
#   - local Windows venv (.venv/Scripts)
#   - local Linux venv   (.venv/bin)
#   - Render (deps in system python, no .venv; env vars injected by platform)
set -euo pipefail
cd "$(dirname "$0")"

# Local: load secrets from gateway/.env. On Render there is no file — the same
# vars are injected by the platform — so this is guarded.
if [ -f .env ]; then set -a; . ./.env; set +a; fi

# Pick the python interpreter and its bin dir.
if   [ -x .venv/Scripts/python.exe ]; then PY=.venv/Scripts/python.exe; BIN=.venv/Scripts
elif [ -x .venv/bin/python ];          then PY=.venv/bin/python;        BIN=.venv/bin
else                                        PY=python;                   BIN=""
fi

# Generate the prisma client from LiteLLM's bundled schema (idempotent).
# Scope the venv bin to THIS command only: on Windows, leaving prisma on the
# launch PATH makes litellm attempt a migration subprocess that can't spawn.
# On Render (Linux) the system bin is already on PATH, so migrations run there.
SCHEMA="$("$PY" -c 'import litellm, os; print(os.path.join(os.path.dirname(litellm.__file__), "proxy", "schema.prisma"))')"
[ -n "$BIN" ] && GEN_PATH="$BIN:$PATH" || GEN_PATH="$PATH"
PATH="$GEN_PATH" "$PY" -m prisma generate --schema "$SCHEMA" || true

# Launch via the litellm console script (has no __main__, can't use -m).
if   [ -n "$BIN" ] && [ -x "$BIN/litellm" ];     then LITELLM="$BIN/litellm"
elif [ -n "$BIN" ] && [ -x "$BIN/litellm.exe" ]; then LITELLM="$BIN/litellm.exe"
else                                                  LITELLM=litellm
fi

# Render provides $PORT; default to 4000 locally.
exec "$LITELLM" --config litellm_config.yaml --port "${PORT:-4000}"
