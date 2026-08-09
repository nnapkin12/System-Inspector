#!/usr/bin/env bash
# Back-compat: install desktop menu + CLI (same as ./install.sh)
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/install.sh" "$@"
