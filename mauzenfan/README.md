# MauZenfan Family Safety Application

MauZenfan is a family safety application designed to provide peace of mind through location tracking, safe zone alerts, emergency notifications, and secure communication. The backend is built using Django and Django REST Framework.

## Project Structure

- `mauzenfan/`: Root project directory.
  - `app/`: (Placeholder for potential future mobile application code or frontend assets)
  - `common/`: (Placeholder for shared libraries or utilities if needed across different project parts)
  - `server/`: Contains the Django backend application.
    - `main_project/`: Django project configuration.
    - `api_app/`: Django app for the core api_app logic.
    - `.env.example`: Template for environment variables.
    - `requirements.txt`: Python dependencies.
    - `manage.py`: Django's command-line utility.

## Development Setup

### Prerequisites

- Python 3.9+
- PostgreSQL (or configure `settings.py` and `.env` for a different database if needed)
- Redis (optional for local development if `REDIS_HOST` is not set in `.env`, but required for Celery tasks and production-like WebSocket communication)

### Environment Setup

1.  **Clone the repository (if you haven't already):**
    ```bash
    git clone <repository_url>
    cd mauzenfan
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    # On Windows: venv\Scripts\activate
    ```

3.  **Install dependencies:**
    Navigate to the server directory and install the required Python packages.
    ```bash
    cd server
    pip install -r requirements.txt
    ```

4.  **Set up environment variables:**
    Copy the example environment file and fill in your actual configuration details.
    ```bash
    cp .env.example .env
    ```
    Now, edit `.env` with your settings for:
    - `DJANGO_SECRET_KEY` (generate a new strong key)
    - `DJANGO_DEBUG` (True for dev, False for prod)
    - `DJANGO_ALLOWED_HOSTS`
    - `DJANGO_CSRF_TRUSTED_ORIGINS`
    - Database credentials (`DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`)
    - Redis connection details (`REDIS_HOST`, `REDIS_PORT`) if you are using it.
    - `FCM_CREDENTIAL_PATH` (path to your Firebase Admin SDK JSON file)
    - `OWM_api_app_KEY` (your OpenWeatherMap api_app key)

    *Note on Redis*: If `REDIS_HOST` is not set in your `.env` file, Django Channels will use an in-memory backend for WebSockets, and Celery might default to `redis://localhost:6379` or fail if Redis is not running. For full functionality including background tasks, ensure Redis is running and `REDIS_HOST` is set.

5.  **Run database migrations:**
    (Ensure your PostgreSQL database server is running and accessible with the credentials provided in `.env`)
    ```bash
    python manage.py migrate
    ```

6.  **Create a superuser (optional, for accessing Django Admin):**
    ```bash
    python manage.py createsuperuser
    ```

## Running the Application

You'll typically need to run the Django development server and, for background tasks and scheduled jobs, the Celery worker and Celery Beat scheduler.

1.  **Start the Django Development Server:**
    (From the `mauzenfan/server/` directory)
    ```bash
    python manage.py runserver
    ```
    The api_app will typically be accessible at `http://localhost:8000` or `http://127.0.0.1:8000`.

2.  **Start the Celery Worker:**
    Open a new terminal, activate the virtual environment, navigate to `mauzenfan/server/`, and run:
    ```bash
    celery -A main_project worker -l info --pool=solo
    ```
    *(The `--pool=solo` option is often useful for development on Windows or simpler setups, adjust as needed for your OS/environment).*

3.  **Start Celery Beat (for scheduled tasks):**
    Open another new terminal, activate the virtual environment, navigate to `mauzenfan/server/`, and run:
    ```bash
    celery -A main_project beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
    ```

## api_app Documentation

Once the development server is running, api_app documentation (powered by drf-spectacular) should be available at:
- Swagger UI: `http://localhost:8000/api_app/schema/swagger-ui/`
- ReDoc: `http://localhost:8000/api_app/schema/redoc/`

The Openapi_app schema can be downloaded from `http://localhost:8000/api_app/schema/`.

## Running Tests
(From the `mauzenfan/server/` directory)
```bash
python manage.py test api_app
```
This will run all tests within the `api_app` application.
