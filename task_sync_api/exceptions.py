from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
from django.utils.timezone import now

def custom_exception_handler(exc, context):
    # Call REST framework's default handler first
    response = exception_handler(exc, context)

    # If response is None or 404, return custom JSON
    if response is None or response.status_code == 404:
        request = context.get('request')
        path = request.get_full_path() if request else ""
        return Response({
            "error": "Task not found",
            "timestamp": now().replace(microsecond=0).isoformat(),  # No microseconds
            "path": path
        }, status=status.HTTP_404_NOT_FOUND)

    return response
