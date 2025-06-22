#!/usr/bin/env bash
set -o errexit

cd /opt/render/project/src
echo "Current directory: $(pwd)"
echo "Directory contents:"
ls -la

python -m venv .venv
source .venv/bin/activate

pip install --upgrade pip

# Install requirements
if [ -f "mauzenfan/requirements.txt" ]; then
    pip install -r mauzenfan/requirements.txt
elif [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
else
    echo "ERROR: Could not find requirements.txt"
    exit 1
fi

# Fix URL references
find . -name "*.py" -exec sed -i "s/include('api_app.urls')/include('apps.api_app.urls')/g" {} +

# Fix drf_spectacular import
find . -name "*.py" -exec sed -i "s/Spectacularapi_appView/SpectacularAPIView/g" {} +

# Fix app configuration
find . -name "*.py" -exec sed -i "s/'api\./'apps.api_app./g" {} +
find . -name "*.py" -exec sed -i "s/api_appConfig/ApiAppConfig/g" {} +

# Debugging
echo "Checking database configuration:"
python -c "import os; print('DATABASE_URL:', os.environ.get('DATABASE_URL'))"

# Fix settings
python -c "
import re
with open('mauzenfan/mauzenfan_config/settings.py', 'r') as f:
    content = f.read()
content = re.sub(r'api_appapps\.ApiAppConfig', 'apps.api_app', content)
content = re.sub(r'apps\.api_app\.apps\.ApiAppConfig', 'apps.api_app', content)
with open('mauzenfan/mauzenfan_config/settings.py', 'w') as f:
    f.write(content)
"

cd mauzenfan/
python manage.py collectstatic --noinput

# Run migrations if DATABASE_URL is set
if [ -n "$DATABASE_URL" ]; then
    python manage.py migrate
else
    echo "WARNING: DATABASE_URL not set. Skipping migrations."
fi