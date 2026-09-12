from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from agents.authentication import AgentAPIKeyAuth
from policy.utils import *
from rest_framework.response import Response


@api_view(['POST'])
@authentication_classes([AgentAPIKeyAuth])
@permission_classes([AllowAny])
def process_spend_request(request):
    if not hasattr(request, 'agent') or request.agent is None:
        return Response({"error": "Authentication required"}, status=401)
    agent_id = request.agent.id
    amount = request.data.get("amount")
    vendor = request.data.get("vendor")
    purpose = request.data.get("purpose", "")
    message, data, status_code = process_spend_request_util(agent_id, amount, vendor, purpose=purpose)
    return Response({"message":message, "data":data}, status=status_code)