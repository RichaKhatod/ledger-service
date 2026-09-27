from django.shortcuts import render
from rest_framework.decorators import api_view
from rest_framework.response import Response
from audit.utils import *


@api_view(['GET'])
def get_anomaly_alerts(request):
    agent_id = request.query_params.get("agent_id")
    message, data, status_code = get_anomaly_alerts_util(agent_id)
    return Response({"message": message, "data": data}, status=status_code)