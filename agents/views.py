from django.shortcuts import render
from rest_framework.decorators import api_view
from rest_framework.response import Response
from agents.utils import *

@api_view(['POST'])
def create_with_key(request):
    name = request.data.get("name")
    agent, raw_key = create_with_key_util(name)
    return Response({"agent_id": agent.id, "name": agent.name,"api_key": raw_key}, status=201)


@api_view(['POST'])
def freeze_agent(request, agent_id):
    message, data, status_code = freeze_agent_util(agent_id)
    return Response({"message": message, "data": data}, status=status_code)


@api_view(['POST'])
def unfreeze_agent(request, agent_id):
    message, data, status_code = unfreeze_agent_util(agent_id)
    return Response({"message": message, "data": data}, status=status_code)