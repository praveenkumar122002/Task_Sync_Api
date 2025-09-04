from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from .models import Task
import uuid

class TaskAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_create_and_get_task(self):
        payload = {"title": "Hello", "description": "desc"}
        r = self.client.post('/api/tasks', payload, format='json')
        self.assertEqual(r.status_code, 201)
        data = r.json()
        self.assertIn('id', data)
        task_id = data['id']
        r2 = self.client.get(f'/api/tasks/{task_id}')
        self.assertEqual(r2.status_code, 200)

    def test_soft_delete(self):
        r = self.client.post('/api/tasks', {"title": "t"}, format='json')
        tid = r.json()['id']
        rdel = self.client.delete(f'/api/tasks/{tid}')
        self.assertEqual(rdel.status_code, 204)
        # ensures is_deleted flag set
        from .models import Task
        t = Task.objects.get(id=tid)
        self.assertTrue(t.is_deleted)
