#!/usr/bin/env bash
# install.sh — One-shot installer for garmin-mcp.
#
# Creates a venv with a compatible Python version (3.10+),
# installs dependencies, and prepares the .env file.
# You still need to fill in your Garmin credentials in .env after running this.
#
# Usage: ./install.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=10

echo "🏃 Installing garmin-mcp at: $REPO_ROOT"
echo ""

# 1. Find a compatible Python (>= 3.10)
#
# Try in order: python3.12, python3.11, python3.10, then python3.
# Use the first one that meets the version requirement.

PYTHON_BIN=""
for candidate in python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    version=$("$candidate" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null)
    major=$(echo "$version" | cut -d. -f1)
    minor=$(echo "$version" | cut -d. -f2)

    if [[ "$major" -gt "$MIN_PYTHON_MAJOR" ]] || \
       { [[ "$major" -eq "$MIN_PYTHON_MAJOR" ]] && [[ "$minor" -ge "$MIN_PYTHON_MINOR" ]]; }; then
      PYTHON_BIN="$(command -v "$candidate")"
      PYTHON_VERSION="$version"
      break
    fi
  fi
done

if [[ -z "$PYTHON_BIN" ]]; then
  echo "❌ No compatible Python found."
  echo ""
  echo "garmin-mcp requires Python ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR} or newer."
  echo ""
  echo "Install options:"
  echo "  • macOS (Homebrew):  brew install python@3.11"
  echo "  • Linux (apt):       sudo apt install python3.11 python3.11-venv"
  echo "  • Direct download:   https://www.python.org/downloads/"
  echo ""
  echo "After installation, re-run this script:  ./install.sh"
  exit 1
fi

echo "✓ Compatible Python found: $PYTHON_BIN (version $PYTHON_VERSION)"

# 2. Create venv
if [[ -d "$REPO_ROOT/venv" ]]; then
  echo "⚠️  Virtual environment already exists at $REPO_ROOT/venv"
  read -p "Recreate it? (y/N) " -n 1 -r REPLY
  echo ""
  if [[ "$REPLY" =~ ^[Yy]$ ]]; then
    rm -rf "$REPO_ROOT/venv"
  else
    echo "Keeping existing venv. Skipping creation."
  fi
fi

if [[ ! -d "$REPO_ROOT/venv" ]]; then
  echo "📦 Creating virtual environment with $PYTHON_BIN..."
  "$PYTHON_BIN" -m venv "$REPO_ROOT/venv"
  echo "✓ venv created at: $REPO_ROOT/venv"
fi

# 3. Install dependencies
echo ""
echo "📦 Installing dependencies..."
"$REPO_ROOT/venv/bin/pip" install --quiet --upgrade pip
"$REPO_ROOT/venv/bin/pip" install -r "$REPO_ROOT/requirements.txt"
echo "✓ Dependencies installed"

# 4. Prepare .env
echo ""
if [[ -f "$REPO_ROOT/.env" ]]; then
  echo "✓ .env already exists — not overwritten"
else
  cp "$REPO_ROOT/.env.example" "$REPO_ROOT/.env"
  echo "✓ .env created from template"
  echo ""
  echo "⚠️  Edit .env now to add your Garmin credentials:"
  echo "   $REPO_ROOT/.env"
fi

# 5. Final instructions
echo ""
echo "✅ Installation complete."
echo ""
echo "Next steps:"
echo ""
echo "1. Edit .env with your Garmin credentials:"
echo "   $REPO_ROOT/.env"
echo ""
echo "2. Test the server starts (Ctrl+C to stop):"
echo "   $REPO_ROOT/venv/bin/python3 $REPO_ROOT/server.py"
echo ""
echo "3. Connect to Claude — see README.md section 'Step 5'."
echo "   Server command: $REPO_ROOT/venv/bin/python3"
echo "   Server args:    $REPO_ROOT/server.py"
echo ""
