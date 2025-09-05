# Task Sync API - Django DRF implementation

## Requirements
- Python 3.10+
- PostgreSQL (or switch to SQLite for local quick test) IN POSTGRESQL,USE YOUR DB PASSWORD
- pip

## Setup (Postgres)


1. Install deps:
   pip install -r requirements.txt

2. Create database in Postgres and user, or change to SQLite in settings.py.

3. Copy .env.example to .env and fill DB credentials.

4. Run migrations:
   python manage.py makemigrations
   python manage.py migrate

5. Run server:
   python manage.py runserver

API base: http://127.0.0.1:8000/api

## Endpoints
- GET /api/tasks
- POST /api/tasks
- GET /api/tasks/{id}
- PUT /api/tasks/{id}
- DELETE /api/tasks/{id}
- POST /api/sync
- GET /api/status
- POST /api/batch

## Sync behavior
- All create/update/delete operations enqueue a `SyncQueueItem`.
- POST /api/sync processes pending queue items in batches (size from SYNC_BATCH_SIZE env var).
- Conflict resolution: last-write-wins using `updated_at`.
- Failed items retry up to MAX_RETRY.

## Tests
python manage.py test

## Notes / assumptions
- Client may provide `id` (UUID) and `updated_at`. Server uses these for conflict resolution.
- server_id gets assigned upon successful server-side acceptance.

Examples:

Get all tasks:

GET http://127.0.0.1:8000/api/tasks/


Create task:

POST http://127.0.0.1:8000/api/tasks/
Content-Type: application/json

{
  "title": "Buy milk",
  "description": "Get from nearby store"
}


Update task:

PUT http://127.0.0.1:8000/api/tasks/<task-id>/
Content-Type: application/json

{
  "title": "Buy milk and eggs",
  "completed": true
}


Delete task:

DELETE http://127.0.0.1:8000/api/tasks/<task-id>/


Trigger sync:

POST http://127.0.0.1:8000/api/sync/


Check sync status:

GET http://127.0.0.1:8000/api/status/


Health check:

GET http://127.0.0.1:8000/api/health/

