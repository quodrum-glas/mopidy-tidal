#!/bin/bash
# Install mopidy-tidal development packages
# Run as: sudo ./install-dev-packages.sh

set -e

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "❌ Please run as root: sudo $0"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TIDALAPI_DIR="$(dirname "$SCRIPT_DIR")/tidalapi"

echo "🔧 Installing development packages..."

# Check if tidalapi directory exists
if [ ! -d "$TIDALAPI_DIR" ]; then
    echo "❌ tidalapi directory not found at: $TIDALAPI_DIR"
    echo "Please ensure both projects are in the same parent directory"
    exit 1
fi

# Install tidalapi first (dependency)
echo "📦 Installing tidalapi (no deps)..."
cd "$TIDALAPI_DIR"
pip install --no-deps -e .

# Install mopidy-tidal
echo "📦 Installing mopidy-tidal (no deps)..."
cd "$SCRIPT_DIR"
pip install --no-deps -e .

# Verify installation
echo "✅ Verifying installation..."
mopidy --version
echo ""
echo "🎵 Development packages installed!"
echo "Run 'mopidy config' to see configuration options"