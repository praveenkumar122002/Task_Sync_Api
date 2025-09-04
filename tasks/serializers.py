from rest_framework import serializers
from .models import Task, SyncQueueItem

class TaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = ['id','title','description','completed','created_at','updated_at','is_deleted','sync_status','server_id','last_synced_at']
        read_only_fields = ['sync_status','server_id','last_synced_at','created_at','updated_at']

class TaskCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = ['id','title','description','completed','created_at','updated_at','is_deleted']
        extra_kwargs = {'title': {'required': True}}

class TaskUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = [
            'id',
            'title',
            'description',
            'completed',
            'is_deleted',
            'updated_at',   # allow client to send updated_at
            'created_at',
            'server_id',
            'sync_status',
            'last_synced_at',
        ]
        read_only_fields = ['created_at', 'server_id', 'sync_status', 'last_synced_at']


class SyncQueueItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = SyncQueueItem
        fields = '__all__'
        read_only_fields = ['id','created_at','processed_at']
