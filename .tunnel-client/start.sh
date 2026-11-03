#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/.."

for cmd in uv op tunnel-client; do
  if ! command -v "$cmd" >/dev/null; then
    printf 'Missing required command: %s\n' "$cmd" >&2
    exit 1
  fi
done

env_file=.tunnel-client/.env.local
if [[ ! -f "$env_file" ]]; then
  printf 'Copy .tunnel-client/.env.example to %s and fill in your settings.\n' "$env_file" >&2
  exit 1
fi
set -a
source "$env_file"
set +a
: "${CONTROL_PLANE_TUNNEL_ID:?Set CONTROL_PLANE_TUNNEL_ID in .tunnel-client/.env.local}"
: "${CONTROL_PLANE_ORGANIZATION_ID:?Set CONTROL_PLANE_ORGANIZATION_ID in .tunnel-client/.env.local}"
: "${TUNNEL_KEY_REF:?Set TUNNEL_KEY_REF in .tunnel-client/.env.local}"
if [[ "$TUNNEL_KEY_REF" != op://* ]]; then
  printf 'TUNNEL_KEY_REF must be a 1Password op:// reference in %s.\n' "$env_file" >&2
  exit 1
fi

unset MCP_LISTEN_ADDR
export CONTROL_PLANE_API_KEY="$TUNNEL_KEY_REF"
cfg=.tunnel-client/local-stdio.yaml
op run -- tunnel-client doctor --config "$cfg"
exec op run -- tunnel-client run --config "$cfg"
