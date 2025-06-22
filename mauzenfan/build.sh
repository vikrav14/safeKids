#!/usr/bin/env bash
set -o errexit

cd /opt/render/project/src
echo "Current directory: $(pwd)"
echo "Directory contents:"
ls -la

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Upgrade pip and install wheel
pip install --upgrade pip wheel

# Install requirements from correct location
REQUIREMENTS_FILE=""
if [ -f "mauzenfan/requirements.txt" ]; then
    REQUIREMENTS_FILE="mauzenfan/requirements.txt"
elif [ -f "requirements.txt" ]; then
    REQUIREMENTS_FILE="requirements.txt"
else
    echo "ERROR: Could not find requirements.txt"
    exit 1
fi

echo "Installing requirements from $REQUIREMENTS_FILE"
pip install -r $REQUIREMENTS_FILE

# Install WhiteNoise explicitly
if ! pip list | grep whitenoise; then
    echo "WhiteNoise not found, installing explicitly..."
    pip install whitenoise==6.6.0
fi

# Build frontend if exists
if [ -d "frontend" ]; then
    echo "Building frontend..."
    cd frontend
    npm install
    npm run build
    cd ..
else
    echo "No frontend directory found. Skipping frontend build."
fi

# Fix URL references
find . -name "*.py" -exec sed -i "s/include('api_app.urls')/include('apps.api_app.urls')/g" {} +

# Fix drf_spectacular import
find . -name "*.py" -exec sed -i "s/Spectacularapi_appView/SpectacularAPIView/g" {} +

# Fix app configuration
find . -name "*.py" -exec sed -i "s/'api\./'apps.api_app./g" {} +
find . -name "*.py" -exec sed -i "s/api_appConfig/ApiAppConfig/g" {} +

# FIX URLS.PY - Replace placeholder syntax with valid code
echo "Fixing urls.py..."
URLS_FILE="mauzenfan/mauzenfan_config/urls.py"
if [ -f "$URLS_FILE" ]; then
    # Replace placeholder syntax with valid view references
    sed -i "s/path('health-check\/', ...),/path('health-check\/', health_check, name='health-check'),/" "$URLS_FILE"
    sed -i "s/    path('api\/', ...),/    path('api\/', include('apps.api_app.urls')),/" "$URLS_FILE"
    
    # Add necessary imports
    sed -i "1s/^/from django.urls import path, re_path, include\n/" "$URLS_FILE"
    sed -i "1s/^/from django.views.generic import TemplateView\n/" "$URLS_FILE"
    sed -i "1s/^/from apps.api_app.views import health_check, root_health_check\n/" "$URLS_FILE"
    sed -i "1s/^/from django.contrib import admin\n/" "$URLS_FILE"
else
    echo "WARNING: urls.py not found at $URLS_FILE"
fi

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

# Go to Django project directory
cd mauzenfan/

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Run migrations if DATABASE_URL is set
if [ -n "$DATABASE_URL" ]; then
    echo "Running database migrations..."
    python manage.py migrate
else
    echo "WARNING: DATABASE_URL not set. Skipping migrations."
fi

# Verify installation
echo "Verifying installed packages:"
pip list