#!/bin/bash
# Install mopidy-tidal development packages (editable, no deps)
# Run as: sudo ./install-dev-packages.sh

set -e

if [ "$EUID" -ne 0 ]; then
    echo "❌ Please run as root: sudo $0"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TIDALAPI_DIR="$(dirname "$SCRIPT_DIR")/tidalapi"

if [ ! -d "$TIDALAPI_DIR" ]; then
    echo "❌ tidalapi directory not found at: $TIDALAPI_DIR"
    exit 1
fi

# Zero out all dependency arrays in pyproject.toml using Python (stdlib only)
nuke_deps() {
    python3 -c "
import tomllib, pathlib, re
p = pathlib.Path('pyproject.toml')
t = p.read_text()
parsed = tomllib.loads(t)
t = re.sub(r'(dependencies\s*=\s*)\[.*?\]', r'\1[]', t, flags=re.DOTALL)
for key in parsed.get('project', {}).get('optional-dependencies', {}):
    t = re.sub(rf'({re.escape(key)}\s*=\s*)\[.*?\]', rf'\1[]', t, flags=re.DOTALL)
p.write_text(t)
"
}

install_no_deps() {
    local dir="$1"
    cd "$dir"
    cp pyproject.toml pyproject.toml.bak
    nuke_deps
    echo "📦 pip install --no-deps -e $dir"
    pip install --no-deps -e . || { mv pyproject.toml.bak pyproject.toml; return 1; }
    mv pyproject.toml.bak pyproject.toml
}

install_no_deps "$TIDALAPI_DIR"
install_no_deps "$SCRIPT_DIR"

echo "✅ Done."
mopidy --version
