from agents.utils import *
from budgets.models import *
from ledger.models import *
from policy.models import *
from rest_framework.test import APIClient
import pytest
from audit.models import *


@pytest.mark.django_db
def test_e2e_full_happy_path():
    # create agent
    client = APIClient()
    response = client.post("/agents/create_with_key/",
        data={"name": "procurement-bot"}, format="json")
    assert response.status_code == 201
    raw_key = response.data["api_key"]
    agent_id = response.data["agent_id"]

    # create budget envelope
    from agents.models import Agent
    agent = Agent.objects.get(id=agent_id)
    BudgetEnvelope.objects.create(
        agent=agent, daily_limit=500_000, monthly_limit=2_000_000,
        per_txn_limit=400_000, auto_approve_threshold=400_000,
    )
    Account.objects.get_or_create(name="Agent Expense", defaults={"type": "expense", "currency": "INR"})
    Account.objects.get_or_create(name="Vendor Payable", defaults={"type": "liability", "currency": "INR"})

    # submit spend request
    agent_client = APIClient()
    agent_client.credentials(HTTP_X_AGENT_KEY=raw_key)
    response = agent_client.post("/policy/process_spend_request/",
        data={"amount": 10_000, "vendor": "aws"}, format="json")
    assert response.status_code == 201

    # verify budget deducted
    envelope = BudgetEnvelope.objects.get(agent=agent)
    assert envelope.spent_today == 10_000

    # verify ledger entries
    from policy.models import SpendRequest
    from ledger.models import Entry
    sr = SpendRequest.objects.last()
    entries = Entry.objects.filter(transaction=sr.transaction)
    assert entries.count() == 2
    assert sum(e.amount for e in entries) == 0

    # verify audit trail
    from audit.models import AuditEvent
    events = AuditEvent.objects.filter(agent=agent)
    event_types = list(events.values_list("event_type", flat=True))
    assert "spend_approved" in event_types
    
    
# test 2 — escalation --> human approval:

@pytest.mark.django_db
def test_e2e_escalation_to_approval():
    # setup
    client = APIClient()
    response = client.post("/agents/create_with_key/",
                           data={"name":"procurement-bot"}, format="json")
    raw_key = response.data["api_key"]
    agent_id = response.data["agent_id"]
    agent = Agent.objects.get(id=agent_id)
    BudgetEnvelope.objects.create(
        agent=agent, daily_limit=500_000, monthly_limit=2_000_000,
        per_txn_limit=400_000, auto_approve_threshold=50_000,
    )
    Account.objects.get_or_create(name="Agent Expense", defaults={"type": "expense", "currency": "INR"})
    Account.objects.get_or_create(name="Vendor Payable", defaults={"type": "liability", "currency": "INR"})
    
    # action1: agent submits over-threshold spend → escalated
    agent_client = APIClient()
    agent_client.credentials(HTTP_X_AGENT_KEY=raw_key)
    response = agent_client.post("/policy/process_spend_request/",
                                 data={"amount":60_000, "vendor":"aws"}, format="json")
    assert response.status_code == 202
    
    # action2: human approval
    approval = ApprovalRequest.objects.last()
    admin_client = APIClient()
    response = admin_client.post(f"/policy/process_approval_decision/{approval.id}/decide/",
                                data={"decision":"approve", "approver_name":"manager"}, format="json")
    assert response.status_code == 200
    
    # verify: budget detected and audit is logged
    envelope = BudgetEnvelope.objects.get(agent=agent)
    assert envelope.spent_today == 60_000
    event_types = list(AuditEvent.objects.filter(agent=agent).values_list("event_type", flat=True))
    assert "spend_escalated" in event_types
    assert "approval_granted" in event_types
    
    
# test 3 --> prompt injection blocked

@pytest.mark.django_db
def test_e2e_prompt_injection_blocked():
    # setup
    client = APIClient()
    response = client.post("/agents/create_with_key/",
                           data={"name":"compromised-bot"}, format="json")
    raw_key = response.data["api_key"]
    agent = Agent.objects.get(id=response.data["agent_id"])
    BudgetEnvelope.objects.create(
            agent=agent, daily_limit=500_000, monthly_limit=2_000_000,
            per_txn_limit=400_000, auto_approve_threshold=400_000,
        )
    
    # ACTION: agent tries to spend ₹50K (over per-txn limit of ₹1K)
    agent_client = APIClient()
    agent_client.credentials(HTTP_X_AGENT_KEY=raw_key)
    response = agent_client.post("/policy/process_spend_request/",
                                    data={"amount":5_000_000, "vendor":"sketchy-service"}, format="json")
    
    # verify: rejected, approved budgets
    assert response.status_code == 403
    envelope = BudgetEnvelope.objects.get(agent=agent)
    assert envelope.spent_today == 0
    assert envelope.spent_this_month == 0
    
    
# test 4: concurrent requests don't overdraft

@pytest.mark.django_db
def test_e2e_concurrent_no_overdraft():
    # setup
    client = APIClient()
    response = client.post("/agents/create_with_key/",
                            data={"name":"compromised-bot"}, format="json")
    raw_key = response.data["api_key"]
    agent = Agent.objects.get(id=response.data["agent_id"])
    BudgetEnvelope.objects.create(
                agent=agent, daily_limit=50_000, monthly_limit=2_000_000,
                per_txn_limit=50_000, auto_approve_threshold=50_000,
            )

    Account.objects.get_or_create(name="Agent Expense", defaults={"type": "expense", "currency": "INR"})
    Account.objects.get_or_create(name="Vendor Payable", defaults={"type": "liability", "currency": "INR"})
    
    agent_client = APIClient()
    agent_client.credentials(HTTP_X_AGENT_KEY=raw_key)
    
    # action: first request takes most of the budget
    request_one = agent_client.post("/policy/process_spend_request/",
                                    data={"amount":10_000, "vendor":"aws"}, format="json")
    print(request_one.data)
    assert request_one.status_code == 201
    
    # action: second request
    request_two = agent_client.post("/policy/process_spend_request/",
                                    data={"amount": 10_000, "vendor": "aws"}, format="json")
    assert request_two.status_code == 201
    
    # action: third request would exceed limit
    request_three = agent_client.post("/policy/process_spend_request/",
                                    data={"amount":35_000, "vendor":"aws"}, format="json")
    assert request_three.status_code == 403

    # verify: budget to not go above daily limit
    envelope = BudgetEnvelope.objects.get(agent=agent)
    assert envelope.spent_today == 20_000
    assert envelope.spent_today <= envelope.daily_limit