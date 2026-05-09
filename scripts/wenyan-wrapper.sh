#!/usr/bin/env bash
# wenyan-wrapper.sh — Inject WeChat AppID/Secret from macOS Keychain (or env)
# and exec the real wenyan CLI.
#
# Install:
#   security add-generic-password -s "md2wechat-appid"  -a "md2wechat" -w "wx..."
#   security add-generic-password -s "md2wechat-secret" -a "md2wechat" -w "..."
#   ln -s "$PWD/scripts/wenyan-wrapper.sh" ~/.local/bin/wenyan
#
# Linux/CI: export WECHAT_APP_ID / WECHAT_APP_SECRET as env vars.
set -euo pipefail

if [[ -z "${WECHAT_APP_ID:-}" ]] && command -v security >/dev/null 2>&1; then
    WECHAT_APP_ID="$(security find-generic-password -s md2wechat-appid -a md2wechat -w 2>/dev/null || true)"
fi
if [[ -z "${WECHAT_APP_SECRET:-}" ]] && command -v security >/dev/null 2>&1; then
    WECHAT_APP_SECRET="$(security find-generic-password -s md2wechat-secret -a md2wechat -w 2>/dev/null || true)"
fi
export WECHAT_APP_ID WECHAT_APP_SECRET

# Find real wenyan in PATH, skipping ourselves
WRAPPER="$(realpath "$0" 2>/dev/null || readlink -f "$0" 2>/dev/null || echo "$0")"
for candidate in $(command -v -a wenyan); do
    real="$(realpath "$candidate" 2>/dev/null || readlink -f "$candidate" 2>/dev/null || echo "$candidate")"
    if [[ "$real" != "$WRAPPER" ]]; then
        exec "$candidate" "$@"
    fi
done

echo "wenyan CLI not found in PATH (excluding wrapper at $WRAPPER)" >&2
exit 127
