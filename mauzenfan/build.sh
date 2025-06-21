#!/usr/bin/env bash
set -o errexit

cd /opt/render/project/src
python -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt

# Fix drf_spectacular import
find . -name "*.py" -exec sed -i "s/Spectacularapi_appView/SpectacularAPIView/g" {} +

# Fix app configuration issues
find . -name "*.py" -exec sed -i "s/'api\./'apps.api_app./g" {} +
find . -name "*.py" -exec sed -i "s/api_appConfig/ApiAppConfig/g" {} +

# Debugging: Show database configuration
echo "Checking database configuration:"
python -c "import os; print('DATABASE_URL:', os.environ.get('DATABASE_URL'))"

# Fix app configuration in settings
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

# Only run migrations if DATABASE_URL is set
if [ -n "$DATABASE_URL" ]; then
    python manage.py migrate
else
    echo "WARNING: DATABASE_URL not set. Skipping migrations."
fi