from django.urls import path
from .views import HealthCheckView, TaskListCreateView, TaskDetailView, SyncTriggerView, SyncStatusView, BatchEndpointView

urlpatterns = [
    path('tasks/', TaskListCreateView.as_view(), name='tasks-list'),
    path('tasks/<uuid:pk>/', TaskDetailView.as_view(), name='task-detail'),
    path('sync/', SyncTriggerView.as_view(), name='sync-trigger'),
    path('status/', SyncStatusView.as_view(), name='sync-status'),
    path('batch/', BatchEndpointView.as_view(), name='batch-endpoint'),
    path('health/', HealthCheckView.as_view(), name='health-check'),
]

