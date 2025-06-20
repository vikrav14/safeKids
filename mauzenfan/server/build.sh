#!/usr/bin/env bash
# exit on error
set -o errexit

# Install dependencies using Poetry - this will handle everything
poetry install --no-interaction --no-ansi

# Run management commands using the virtualenv Python
/opt/render/project/src/.venv/bin/python manage.py collectstatic --noinput
/opt/render/project/src/.venv/bin/python manage.py migrate