#!/usr/bin/env bash
set -o errexit

cd /opt/render/project/src
python -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install -r mauzenfan/server/requirements.txt

# Debugging: Show database configuration
echo "Checking database configuration:"
python -c "import os; print('DATABASE_URL:', os.environ.get('DATABASE_URL'))"

cd mauzenfan/
python manage.py collectstatic --noinput

# Only run migrations if DATABASE_URL is set
if [ -n "$DATABASE_URL" ]; then
    python manage.py migrate
else
    echo "WARNING: DATABASE_URL not set. Skipping migrations."
fi