import uuid
from django.utils import timezone
from django.conf import settings
from .models import Task, SyncQueueItem
from django.db import transaction
from dateutil import parser as dateparser
from django.db.models import Q
import logging

logger = logging.getLogger(__name__)

# helper: snapshot
def _task_snapshot_from_instance(task: Task):
    return {
        "id": str(task.id),
        "title": task.title,
        "description": task.description,
        "completed": task.completed,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        "is_deleted": task.is_deleted,
        "server_id": task.server_id,
    }

def enqueue_operation(operation: str, task_id, snapshot: dict):
    # store queue item
    return SyncQueueItem.objects.create(operation=operation, task_id=task_id, task_snapshot=snapshot)

# Task CRUD operations (server-side)
def create_task(data: dict, from_client=True):
    """
    data: may include 'id' (client uuid). If from_client True, we expect client provided id.
    """
    client_id = data.get('id')
    if client_id:
        client_id = uuid.UUID(client_id)
    else:
        client_id = uuid.uuid4()

    task, created = Task.objects.get_or_create(id=client_id, defaults={
        'title': data.get('title', ''),
        'description': data.get('description', ''),
        'completed': data.get('completed', False),
        'created_at': data.get('created_at', timezone.now()),
        'updated_at': data.get('updated_at', timezone.now()),
        'is_deleted': data.get('is_deleted', False),
        'sync_status': 'pending'
    })
    if not created:
        # if exists, update with incoming (last-write-wins managed during sync)
        task.title = data.get('title', task.title)
        task.description = data.get('description', task.description)
        task.completed = data.get('completed', task.completed)
        task.is_deleted = data.get('is_deleted', task.is_deleted)
        task.sync_status = 'pending'
        task.updated_at = data.get('updated_at', timezone.now())
        task.save()
    else:
        # created new -> enqueue create
        enqueue_operation('create', task.id, _task_snapshot_from_instance(task))
    return task

def update_task(task_id, data: dict):
    try:
        task = Task.objects.get(id=task_id)
    except Task.DoesNotExist:
        return None
    # update fields
    task.title = data.get('title', task.title)
    task.description = data.get('description', task.description)
    task.completed = data.get('completed', task.completed)
    task.is_deleted = data.get('is_deleted', task.is_deleted)
    # client may send updated_at; use it so sync can apply last-write-wins
    if data.get('updated_at'):
        try:
            task.updated_at = dateparser.parse(data.get('updated_at'))
        except Exception:
            task.updated_at = timezone.now()
    else:
        task.updated_at = timezone.now()
    task.sync_status = 'pending'
    task.save()
    enqueue_operation('update', task.id, _task_snapshot_from_instance(task))
    return task

def delete_task_soft(task_id):
    try:
        task = Task.objects.get(id=task_id)
    except Task.DoesNotExist:
        return False
    task.is_deleted = True
    task.sync_status = 'pending'
    task.updated_at = timezone.now()
    task.save()
    enqueue_operation('delete', task.id, _task_snapshot_from_instance(task))
    return True

# Sync orchestration
def _apply_server_assignments(task: Task):
    # assign a server_id when newly created on server-side. server_id format: srv_<uuid4>
    if not task.server_id:
        task.server_id = f"srv_{uuid.uuid4().hex[:12]}"
    task.last_synced_at = timezone.now()
    task.sync_status = 'synced'
    task.save()

def process_sync_batch(items: list):
    """
    Process a list of SyncQueueItem instances.
    Conflict resolution: last-write-wins based on updated_at timestamps.
    Returns dict with summary in company API format.
    """
    summary = {"processed": 0, "failed": 0, "errors": []}
    max_retry = getattr(settings, "MAX_RETRY", 3)

    for item in items:
        try:
            item.status = "processing"
            item.save()

            snap = item.task_snapshot
            op = item.operation
            client_task_id = uuid.UUID(str(item.task_id))

            client_updated_at = None
            if snap.get("updated_at"):
                try:
                    client_updated_at = dateparser.parse(snap.get("updated_at"))
                except Exception:
                    client_updated_at = timezone.now()

            server_task = Task.objects.filter(id=client_task_id).first()

            if op == "create":
                if not server_task:
                    # create new task
                    server_task = Task(
                        id=client_task_id,
                        title=snap.get("title", ""),
                        description=snap.get("description", ""),
                        completed=snap.get("completed", False),
                        created_at = snap.get("created_at") and dateparser.parse(snap.get("created_at")) or timezone.now(),
                        updated_at = client_updated_at or timezone.now(),
                        is_deleted = snap.get("is_deleted", False),
                        sync_status = "synced",
                    )
                    server_task.save()
                    _apply_server_assignments(server_task)
                else:
                    # conflict: last-write-wins
                    if client_updated_at and client_updated_at > server_task.updated_at:
                        server_task.title = snap.get("title", server_task.title)
                        server_task.description = snap.get("description", server_task.description)
                        server_task.completed = snap.get("completed", server_task.completed)
                        server_task.is_deleted = snap.get("is_deleted", server_task.is_deleted)
                        server_task.updated_at = client_updated_at
                        server_task.sync_status = "synced"
                        server_task.save()
                        _apply_server_assignments(server_task)
                    else:
                        # conflict resolved: server wins
                        summary["errors"].append({
                            "task_id": str(server_task.id),
                            "operation": op,
                            "error": "Conflict resolved using last-write-wins",
                            "timestamp": timezone.now().isoformat().replace("+00:00", "Z")
                        })

            elif op == "update":
                if not server_task:
                    # create missing server task
                    server_task = Task(
                        id=client_task_id,
                        title=snap.get("title", ""),
                        description=snap.get("description", ""),
                        completed=snap.get("completed", False),
                        created_at = snap.get("created_at") and dateparser.parse(snap.get("created_at")) or timezone.now(),
                        updated_at = client_updated_at or timezone.now(),
                        is_deleted = snap.get("is_deleted", False),
                        sync_status = "synced",
                    )
                    server_task.save()
                    _apply_server_assignments(server_task)
                else:
                    if client_updated_at and client_updated_at >= server_task.updated_at:
                        server_task.title = snap.get("title", server_task.title)
                        server_task.description = snap.get("description", server_task.description)
                        server_task.completed = snap.get("completed", server_task.completed)
                        server_task.is_deleted = snap.get("is_deleted", server_task.is_deleted)
                        server_task.updated_at = client_updated_at
                        server_task.sync_status = "synced"
                        server_task.save()
                        _apply_server_assignments(server_task)
                    else:
                        # server wins
                        summary["errors"].append({
                            "task_id": str(server_task.id),
                            "operation": op,
                            "error": "Conflict resolved using last-write-wins",
                            "timestamp": timezone.now().isoformat().replace("+00:00", "Z")
                        })

            elif op == "delete":
                if server_task:
                    if client_updated_at and client_updated_at >= server_task.updated_at:
                        server_task.is_deleted = True
                        server_task.updated_at = client_updated_at
                        server_task.sync_status = "synced"
                        server_task.save()
                        _apply_server_assignments(server_task)
                    else:
                        # server wins
                        summary["errors"].append({
                            "task_id": str(server_task.id),
                            "operation": op,
                            "error": "Conflict resolved using last-write-wins",
                            "timestamp": timezone.now().isoformat().replace("+00:00", "Z")
                        })
                # else: nothing to delete

            item.status = "done"
            item.processed_at = timezone.now()
            item.save()
            summary["processed"] += 1

        except Exception as ex:
            logger.exception(f"Error processing queue item {item.id}: {ex}")
            item.retry_count += 1
            item.status = "failed" if item.retry_count >= max_retry else "pending"
            item.save()
            summary["failed"] += 1
            summary["errors"].append({
                "task_id": str(item.task_id),
                "operation": item.operation,
                "error": str(ex),
                "timestamp": timezone.now().isoformat().replace("+00:00", "Z")
            })

    return summary

def fetch_pending_queue(batch_size=None):
    if batch_size is None:
        batch_size = getattr(settings, "SYNC_BATCH_SIZE", 50)
    return list(SyncQueueItem.objects.filter(status='pending').order_by('created_at')[:batch_size])

def pending_sync_count():
    return SyncQueueItem.objects.filter(status='pending').count()
