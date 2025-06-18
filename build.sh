#!/usr/bin/env bash
# exit on error
set -o errexit

# These commands will run from the 'Root Directory' you set in Render (mauzenfan/server)
pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate