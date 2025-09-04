import uuid
from django.db import models
from django.utils import timezone
from django.utils.timezone import now

SYNC_STATUS_CHOICES = [
    ('pending', 'Pending'),
    ('synced', 'Synced'),
    ('error', 'Error'),
]

OPERATION_CHOICES = [
    ('create', 'Create'),
    ('update', 'Update'),
    ('delete', 'Delete'),
]

class Task(models.Model):
    # client-generated UUID (so offline client can create & keep same id)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)
    is_deleted = models.BooleanField(default=False)
    sync_status = models.CharField(max_length=10, choices=SYNC_STATUS_CHOICES, default='pending')
    server_id = models.CharField(max_length=100, blank=True, null=True)
    last_synced_at = models.DateTimeField(blank=True, null=True)

    def soft_delete(self):
        self.is_deleted = True
        self.sync_status = 'pending'
        self.updated_at = timezone.now()
        self.save()

    def save(self, *args, **kwargs):
        # ensure updated_at on every save unless explicitly set
        if not self.updated_at:
            self.updated_at = timezone.now()
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)

class SyncQueueItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    operation = models.CharField(max_length=10, choices=OPERATION_CHOICES)
    task_id = models.UUIDField()  # client task id (UUID)
    task_snapshot = models.JSONField()  # full snapshot of task state at operation time
    retry_count = models.IntegerField(default=0)
    status = models.CharField(max_length=10, default='pending')  # pending, processing, done, failed
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['created_at']

class SyncLog(models.Model):
    timestamp = models.DateTimeField(default=now)
    processed = models.IntegerField(default=0)
    failed = models.IntegerField(default=0)