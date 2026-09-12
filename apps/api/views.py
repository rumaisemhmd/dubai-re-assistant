from rest_framework.response import Response
from rest_framework.views import APIView


class HealthCheckView(APIView):
    """Simple liveness check used for deployment monitoring."""

    def get(self, request):
        return Response({"status": "ok"})
