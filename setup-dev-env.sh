#!/bin/bash
# Audiophile Arch Linux Development Setup
# Installs system packages for mopidy-tidal development
# Run as: sudo ./setup-dev-env.sh

set -e

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "❌ Please run as root: sudo $0"
    exit 1
fi

# Get the original user (who called sudo)
ORIG_USER=${SUDO_USER:-$USER}

echo "🎵 Setting up Audiophile Arch Linux for Mopidy-Tidal development..."
echo "👤 Installing for user: $ORIG_USER"

# Core Python and Mopidy
echo "📦 Installing core packages..."
pacman -S --needed python python-pip mopidy python-requests

# Audio/media dependencies
echo "🔊 Installing GStreamer and audio plugins..."
pacman -S --needed gstreamer gst-plugins-base gst-plugins-good gst-plugins-bad gst-plugins-ugly

# Development tools
echo "🛠️ Installing development tools..."
pacman -S --needed python-pytest git

# AUR packages (run as original user)
echo "📚 Installing AUR packages..."
su - "$ORIG_USER" -c "yay -S --needed python-cachetools python-tenacity python-pywidevine"

# Optional: Audio analysis tools
echo "🎛️ Installing optional audio tools..."
sudo pacman -S --needed sox ffmpeg

echo "✅ System packages installed!"
echo ""
echo "Next steps:"
echo "1. cd /path/to/tidalapi && sudo pip install --no-deps -e ."
echo "2. cd /path/to/mopidy-tidal && sudo pip install --no-deps -e ."
echo "3. Test with: mopidy --version"
echo ""
echo "🎵 Ready for audiophile development!"