#!/usr/bin/env bash
# Run the pinned compiler; BEND_REPO may point to another Bend checkout.
set -euo pipefail
PLAYGROUND_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BEND_REPO="${BEND_REPO:-$PLAYGROUND_ROOT/upstream/bend}"
if [[ ! -f "$BEND_REPO/bend2/main.ts" ]]; then
  echo 'Bend compiler not found. Run `just setup` or set BEND_REPO to a Bend checkout.' >&2
  exit 1
fi
exec bun "$BEND_REPO/bend2/main.ts" "$@"
