#!/usr/bin/env bash
# exit on error
set -o errexit

# Navigate to the project root
cd /opt/render/project/src

# Debugging: Show directory structure
echo "Current directory: $(pwd)"
echo "Directory structure:"
find . -maxdepth 3 -type d -print | sort | sed 's/[^/]*\//|   /g'

# Create virtual environment
python -m venv .venv

# Upgrade pip
.venv/bin/pip install --upgrade pip

# Install dependencies from requirements.txt
echo "Installing dependencies..."
.venv/bin/pip install -r requirements.txt

# Find manage.py location
MANAGE_PATH=$(find . -name manage.py -print -quit)
if [ -z "$MANAGE_PATH" ]; then
    echo "Error: Could not find manage.py"
    exit 1
fi

# Navigate to Django project directory
MANAGE_DIR=$(dirname "$MANAGE_PATH")
echo "Changing to Django project directory: $MANAGE_DIR"
cd "$MANAGE_DIR"

# Run management commands
echo "Running migrations and collectstatic..."
/opt/render/project/src/.venv/bin/python manage.py collectstatic --noinput
/opt/render/project/src/.venv/bin/python manage.py migrate