#!/usr/bin/env bash
# exit on error
set -o errexit

# Navigate to the project root
cd /opt/render/project/src

# Debugging: Show environment info
echo "Current directory: $(pwd)"
echo "Python version: $(python --version)"
echo "Pip version: $(pip --version)"
echo "Directory contents:"
ls -la

# Create virtual environment using explicit path
VENV_PATH="/opt/render/project/src/.venv"
python -m venv "$VENV_PATH"

# Use virtual environment's pip with absolute path
"$VENV_PATH/bin/pip" install --upgrade pip

# Find requirements.txt file
REQUIREMENTS_FILE=$(find . -name requirements.txt -print -quit)
if [ -z "$REQUIREMENTS_FILE" ]; then
    echo "Error: Could not find requirements.txt in the repository"
    echo "Searching for requirements.txt:"
    find . -name requirements.txt
    exit 1
fi

echo "Found requirements.txt at: $REQUIREMENTS_FILE"

# Install dependencies from requirements.txt
echo "Installing dependencies..."
"$VENV_PATH/bin/pip" install -r "$REQUIREMENTS_FILE"

# Find manage.py location
MANAGE_PY=$(find . -name manage.py -print -quit)
if [ -z "$MANAGE_PY" ]; then
    echo "Error: Could not find manage.py"
    echo "Searching for manage.py:"
    find . -name manage.py
    exit 1
fi

# Navigate to directory containing manage.py
MANAGE_DIR=$(dirname "$MANAGE_PY")
echo "Changing to directory: $MANAGE_DIR"
cd "$MANAGE_DIR"

# Run management commands
echo "Running migrations and collectstatic..."
"$VENV_PATH/bin/python" manage.py collectstatic --noinput
"$VENV_PATH/bin/python" manage.py migrate