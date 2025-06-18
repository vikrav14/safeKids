#!/usr/bin/env bash
# exit on error
set -o errexit

# Install dependencies using the default pip
pip install -r requirements.txt

# Now, use the EXPLICIT path to the python in the virtualenv for all manage.py commands
/opt/render/project/src/.venv/bin/python manage.py collectstatic --noinput
/opt/render/project/src/.venv/bin/python manage.py migrate