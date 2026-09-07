from django.shortcuts import render
from rest_framework.decorators import api_view
from rest_framework.response import Response
from budgets.utils import *

@api_view(['GET'])
def get_budget(request, agent_id):
    message, data, status_code = get_budget_util(agent_id)
    return Response({"message": message, "data": data}, status=status_code)


@api_view(['PATCH'])
def update_budget(request, agent_id):
    message, data, status_code = update_budget_util(agent_id, request.data)
    return Response({"message": message, "data": data}, status=status_code)