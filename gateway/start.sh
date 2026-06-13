#!/usr/bin/env bash
# Start the LiteLLM gateway from its own folder + venv.
#
# Because this venv lives under gateway/, LiteLLM's dotenv discovery walks up
# into gateway/.env.litellm (NOT the app's backend/.env) — so the old "proxy
# grabbed the app's neondb" collision can't happen here. No export-precedence
# hack needed.
set -euo pipefail
cd "$(dirname "$0")"

# Local: load secrets from gateway/.env. On Render the same vars are injected
# by the platform (no file), so this is guarded — don't rely on implicit
# dotenv discovery.
if [ -f .env ]; then set -a; . ./.env; set +a; fi

PY=.venv/Scripts/python.exe
[ -f "$PY" ] || PY=.venv/bin/python    # Linux (Render) path

# Generate the prisma client from LiteLLM's bundled schema (idempotent).
SCHEMA="$("$PY" -c 'import litellm, os; print(os.path.join(os.path.dirname(litellm.__file__), "proxy", "schema.prisma"))')"
PATH="$(dirname "$PY"):$PATH" "$PY" -m prisma generate --schema "$SCHEMA" || true

# litellm has no __main__; launch via its console script (Windows .exe / Linux).
LITELLM="$(dirname "$PY")/litellm"
[ -f "$LITELLM" ] || LITELLM="$(dirname "$PY")/litellm.exe"

# Render provides $PORT; default to 4000 locally.
exec "$LITELLM" --config litellm_config.yaml --port "${PORT:-4000}"
