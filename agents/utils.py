import hashlib
from agents.models import Agent
import secrets
from rest_framework.response import Response
from rest_framework import status
from policy.models import ApprovalRequest, SpendRequest
from django.utils import timezone


def hash_key(api_key_hash):
    key_bytes = api_key_hash.encode('utf-8')
    return hashlib.sha256(key_bytes).hexdigest()


def create_with_key_util(name):
    raw_key = secrets.token_hex(32)
    # raw_key = f"agent_{secrets.token_hex(32)}"
    hashed_key = hash_key(raw_key)
    agent = Agent.objects.create(
        name=name,
        api_key_hash=hashed_key
    )
    
    response = (agent, raw_key)
    
    return response


def freeze_agent_util(agent_id):
    agent = Agent.objects.get(id=agent_id)
    agent.is_active = False
    agent.save(update_fields=["is_active"])
    # auto-deny all pending approvals for this agent
    pending = ApprovalRequest.objects.filter(
        spend_request__agent_id=agent_id,
        decision="pending",
    )
    count = pending.count()
    for approval in pending:
        approval.decision = "denied"
        approval.decided_at = timezone.now()
        approval.save(update_fields=["decision", "decided_at"])
        approval.spend_request.status = "rejected"
        approval.spend_request.save(update_fields=["status"])

    return ("Agent frozen", {"agent_id": agent.id, "approvals_denied": count}, 200)


def unfreeze_agent_util(agent_id):
    agent = Agent.objects.get(id=agent_id)
    agent.is_active = True
    agent.save(update_fields=["is_active"])
    return ("Agent unfrozen", {"agent_id":agent.id}, 200)