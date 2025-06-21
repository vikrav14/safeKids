#!/usr/bin/env bash
set -o errexit

cd /opt/render/project/src
echo "Current directory: $(pwd)"
echo "Directory contents:"
ls -la  # Debug: show files in current directory

python -m venv .venv
source .venv/bin/activate

pip install --upgrade pip

# Find and install requirements.txt
if [ -f "mauzenfan/requirements.txt" ]; then
    pip install -r mauzenfan/requirements.txt
elif [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
else
    echo "ERROR: Could not find requirements.txt"
    exit 1
fi

# Fix drf_spectacular import
find . -name "*.py" -exec sed -i "s/Spectacularapi_appView/SpectacularAPIView/g" {} +

# Fix app configuration issues
find . -name "*.py" -exec sed -i "s/'api\./'apps.api_app./g" {} +
find . -name "*.py" -exec sed -i "s/api_appConfig/ApiAppConfig/g" {} +

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