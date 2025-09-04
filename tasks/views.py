from rest_framework.views import APIView
from rest_framework.response import Response
from django.utils.timezone import now
from rest_framework import status
from .models import SyncLog, Task, SyncQueueItem
from .serializers import TaskSerializer, TaskCreateSerializer, SyncQueueItemSerializer
from . import services
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.utils import timezone

class TaskListCreateView(APIView):
    def get(self, request):
        qs = Task.objects.filter(is_deleted=False).order_by('-updated_at')
        serializer = TaskSerializer(qs, many=True)
        return Response(serializer.data)

    def post(self, request):
        # Accept client-generated ID in payload
        serializer = TaskCreateSerializer(data=request.data)
        if serializer.is_valid():
            data = serializer.validated_data
            # create and enqueue
            task = services.create_task(data)
            out = TaskSerializer(task).data
            return Response(out, status=status.HTTP_201_CREATED)
        return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

class TaskDetailView(APIView):
    def get(self, request, pk):
        task = get_object_or_404(Task, id=pk)
        serializer = TaskSerializer(task)
        return Response(serializer.data)

    def put(self, request, pk):
        task = get_object_or_404(Task, id=pk)
        data = request.data
        updated = services.update_task(pk, data)
        if not updated:
            return Response({"error": "Task not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(TaskSerializer(updated).data)

    def delete(self, request, pk):
        ok = services.delete_task_soft(pk)
        if not ok:
            return Response({"error": "Task not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)

# Sync endpoints
class SyncTriggerView(APIView):
    """
    POST /api/sync  -> triggers processing of pending queue items in batches
    """
    def post(self, request):
        batch_size = int(request.data.get('batch_size', settings.SYNC_BATCH_SIZE))
        total_processed = 0
        total_failed = 0
        errors = []

        pending = SyncQueueItem.objects.filter(status='pending').order_by('created_at')[:batch_size]
        summary = services.process_sync_batch(pending)
        total_processed += summary.get('processed', 0)
        total_failed += summary.get('failed', 0)
        errors.extend(summary.get('errors', []))

        # create a SyncLog entry for last sync
        from .models import SyncLog
        SyncLog.objects.create(
            timestamp=timezone.now(), 
            processed=total_processed, 
            failed=total_failed
        )

        return Response({
            "success": True,
            "synced_items": total_processed,
            "failed_items": total_failed,
            "errors": errors
        })


class SyncStatusView(APIView):
    def get(self, request):
        # Pending sync items in the queue
        pending_sync_count = SyncQueueItem.objects.filter(status="pending").count()

        # Last processed sync timestamp from SyncLog
        last_log = SyncLog.objects.order_by('-timestamp').first()
        last_sync_timestamp = last_log.timestamp.isoformat().replace("+00:00", "Z") if last_log else None

        # Total items in the queue
        sync_queue_size = SyncQueueItem.objects.count()

        return Response({
            "pending_sync_count": pending_sync_count,
            "last_sync_timestamp": last_sync_timestamp,
            "is_online": True,
            "sync_queue_size": sync_queue_size
        })


class BatchEndpointView(APIView):
    """
    POST /api/batch
    This endpoint emulates a server's batch processor that client might call.
    The client sends 'items' with operation and data and server processes and returns processed_items array.
    """
    def post(self, request):
        items = request.data.get('items', [])
        processed_items = []
        for it in items:
            client_id = it.get('task_id')
            op = it.get('operation')
            data = it.get('data', {})
            # apply operations using same service logic (server-side)
            try:
                if op == 'create':
                    task = services.create_task({**data, "id": client_id})
                    services._apply_server_assignments(task)
                    # Make resolved_data.id = server_id
                    resolved_data = TaskSerializer(task).data
                    resolved_data['id'] = task.server_id
                    processed_items.append({
                        "client_id": client_id,
                        "server_id": task.server_id,
                        "status": "success",
                        "resolved_data": resolved_data
                    })

                elif op == 'update':
                    task = services.update_task(client_id, {**data})
                    services._apply_server_assignments(task)
                    resolved_data = TaskSerializer(task).data
                    resolved_data['id'] = task.server_id
                    processed_items.append({
                        "client_id": client_id,
                        "server_id": task.server_id,
                        "status": "success",
                        "resolved_data": resolved_data
                    })

                elif op == 'delete':
                    ok = services.delete_task_soft(client_id)
                    processed_items.append({
                        "client_id": client_id,
                        "status": "success"
                    })
                else:
                    processed_items.append({
                        "client_id": client_id,
                        "status": "error",
                        "error": "unknown operation"
                    })
            except Exception as ex:
                processed_items.append({
                    "client_id": client_id,
                    "status": "error",
                    "error": str(ex)
                })

        return Response({"processed_items": processed_items})

class HealthCheckView(APIView):
    """
    GET /api/health
    Simple health check endpoint
    """
    def get(self, request):
        return Response({
            "status": "ok",
            "is_online": True,
            "timestamp": timezone.now().isoformat().replace("+00:00", "Z")
        })
