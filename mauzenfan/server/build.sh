#!/usr/bin/env bash
set -o errexit

# Navigate to project root
cd /opt/render/project/src

# Create virtual environment
python -m venv .venv

# Use absolute paths
VENV_PYTHON="/opt/render/project/src/.venv/bin/python"
VENV_PIP="/opt/render/project/src/.venv/bin/pip"

# Upgrade pip and setuptools
$VENV_PIP install --upgrade pip setuptools

# Find requirements.txt
REQUIREMENTS_FILE=$(find . -name requirements.txt -print -quit)
if [ -z "$REQUIREMENTS_FILE" ]; then
    echo "Error: requirements.txt not found"
    find . -type f -name '*.txt'
    exit 1
fi
echo "Found requirements: $REQUIREMENTS_FILE"

# Install dependencies
$VENV_PIP install -r "$REQUIREMENTS_FILE"

# Find manage.py
MANAGE_FILE=$(find . -name manage.py -print -quit)
if [ -z "$MANAGE_FILE" ]; then
    echo "Error: manage.py not found"
    find . -type f -name '*.py'
    exit 1
fi
MANAGE_DIR=$(dirname "$MANAGE_FILE")
echo "Found manage.py in: $MANAGE_DIR"

# Run Django commands
cd "$MANAGE_DIR"
$VENV_PYTHON manage.py collectstatic --noinput
$VENV_PYTHON manage.py migrate