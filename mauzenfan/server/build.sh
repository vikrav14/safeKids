#!/usr/bin/env bash
# exit on error
set -o errexit

# Navigate to project root where pyproject.toml should be
cd /opt/render/project/src

# Install dependencies using Poetry
poetry install --no-interaction --no-ansi

# Move to your Django project directory
cd mauzenfan/server

# Run management commands
/opt/render/project/src/.venv/bin/python manage.py collectstatic --noinput
/opt/render/project/src/.venv/bin/python manage.py migrate