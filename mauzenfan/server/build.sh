#!/usr/bin/env bash
# exit on error
set -o errexit

# Install system dependencies
sudo apt-get update
sudo apt-get install -y libpq-dev build-essential python3-dev

# Use Poetry for Python dependency management
poetry install --no-interaction --no-ansi

# Now, use the explicit path to the python in the virtualenv
/opt/render/project/src/.venv/bin/python manage.py collectstatic --noinput
/opt/render/project/src/.venv/bin/python manage.py migrate