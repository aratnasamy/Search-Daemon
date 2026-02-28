#!/usr/bin/env bash
set -euo pipefail

PLIST_LABEL="com.search-daemon"
PLIST_DEST="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_PATH="$HOME/.config/search-daemon/config.yaml"
LOG_PATH="$HOME/.cache/search-mcp/daemon.log"

UV_PATH="$(which uv 2>/dev/null || true)"
if [[ -z "$UV_PATH" ]]; then
    echo "ERROR: 'uv' not found in PATH. Install it with: curl -Ls https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# Create config dir and copy example config if not already present
mkdir -p "$(dirname "$CONFIG_PATH")"
if [[ ! -f "$CONFIG_PATH" ]]; then
    cp "$PROJECT_DIR/config.yaml" "$CONFIG_PATH"
    echo "Created default config at $CONFIG_PATH — edit it to set your folders."
fi

# Create log dir
mkdir -p "$(dirname "$LOG_PATH")"

# Unload existing service if running
if launchctl list "$PLIST_LABEL" &>/dev/null; then
    echo "Unloading existing service..."
    launchctl unload "$PLIST_DEST" 2>/dev/null || true
fi

# Write plist with substituted values
sed \
    -e "s|__UV_PATH__|$UV_PATH|g" \
    -e "s|__PROJECT_DIR__|$PROJECT_DIR|g" \
    -e "s|__CONFIG_PATH__|$CONFIG_PATH|g" \
    -e "s|__LOG_PATH__|$LOG_PATH|g" \
    "$PROJECT_DIR/com.search-daemon.plist" > "$PLIST_DEST"

# Install dependencies
echo "Installing dependencies with uv..."
cd "$PROJECT_DIR"
uv sync

# Load the daemon service
launchctl load "$PLIST_DEST"

# --- Menu bar ---
MENU_PLIST_LABEL="com.search-daemon.menu-bar"
MENU_PLIST_DEST="$HOME/Library/LaunchAgents/${MENU_PLIST_LABEL}.plist"

if launchctl list "$MENU_PLIST_LABEL" &>/dev/null; then
    launchctl unload "$MENU_PLIST_DEST" 2>/dev/null || true
fi

sed \
    -e "s|__UV_PATH__|$UV_PATH|g" \
    -e "s|__PROJECT_DIR__|$PROJECT_DIR|g" \
    "$PROJECT_DIR/com.search-menu-bar.plist" > "$MENU_PLIST_DEST"

launchctl load "$MENU_PLIST_DEST"

echo ""
echo "Services installed and started."
echo "  Config:    $CONFIG_PATH"
echo "  Log:       $LOG_PATH"
echo "  Daemon:    launchctl list $PLIST_LABEL"
echo "  Menu bar:  launchctl list $MENU_PLIST_LABEL"
echo "  Stop all:  launchctl unload $PLIST_DEST $MENU_PLIST_DEST"
