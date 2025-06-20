#!/usr/bin/env bash
# exit on error
set -o errexit

# Create virtual environment
python -m venv /opt/render/project/src/.venv

# Use virtual environment's pip
/opt/render/project/src/.venv/bin/pip install --upgrade pip

# Install dependencies from requirements.txt
/opt/render/project/src/.venv/bin/pip install -r requirements.txt

# Move to Django project directory
cd mauzenfan/server

# Run management commands
/opt/render/project/src/.venv/bin/python manage.py collectstatic --noinput
/opt/render/project/src/.venv/bin/python manage.py migrate