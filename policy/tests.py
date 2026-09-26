from django.test import TestCase
from agents.utils import *
from budgets.models import *
from ledger.models import *
from policy.models import *
from rest_framework.test import APIClient
import pytest
from django.utils import timezone
from datetime import timedelta


def helper():
    agent, raw_key = create_with_key_util("test-agent")
    BudgetEnvelope.objects.create(
        agent=agent, daily_limit=500_000, monthly_limit=2_000_000,
        per_txn_limit=100_000, auto_approve_threshold=50_000,
    )
    Account.objects.create(name="Agent Expense", type="expense", currency="INR")
    Account.objects.create(name="Vendor Payable", type="liability", currency="INR")
    client = APIClient()
    client.credentials(HTTP_X_AGENT_KEY=raw_key)
    return agent, client
    
    
@pytest.mark.django_db
def test_approve_within_limits():
    agent, client = helper()
    response = client.post("/policy/process_spend_request/",
                           data = {"amount":10000, "vendor":"aws"}, format="json")
    assert response.status_code==201


@pytest.mark.django_db
def test_budget_deduction_on_approve():
    agent, client = helper()
    client.post("/policy/process_spend_request/",
        data={"amount": 10_000, "vendor": "aws"}, format="json")
    envelope = BudgetEnvelope.objects.get(agent=agent)
    assert envelope.spent_today == 10_000
    assert envelope.spent_this_month == 10_000


@pytest.mark.django_db
def test_ledger_entries_created():
    agent, client = helper()
    response = client.post("/policy/process_spend_request/",
        data={"amount": 10_000, "vendor": "aws"}, format="json")
    from ledger.models import Entry
    # get the transaction id from response or from SpendRequest
    from policy.models import SpendRequest
    sr = SpendRequest.objects.last()
    entries = Entry.objects.filter(transaction=sr.transaction)
    assert entries.count() == 2
    assert sum(e.amount for e in entries) == 0


@pytest.mark.django_db
def test_reject_over_per_txn_limit():
    agent, client = helper()
    response = client.post("/policy/process_spend_request/",
        data={"amount": 200_000, "vendor": "aws"}, format="json")
    assert response.status_code == 403


@pytest.mark.django_db
def test_reject_over_daily_limit():
    agent, client = helper()
    envelope = BudgetEnvelope.objects.get(agent=agent)
    envelope.spent_today = 450_000
    envelope.save(update_fields=["spent_today"])
    response = client.post("/policy/process_spend_request/",
        data={"amount": 60_000, "vendor": "aws"}, format="json")
    assert response.status_code == 403


@pytest.mark.django_db
def test_reject_dont_deduct_budget():
    agent, client = helper()
    client.post("/policy/process_spend_request/",
        data={"amount": 200_000, "vendor": "aws"}, format="json")  # exceeds per_txn_limit
    envelope = BudgetEnvelope.objects.get(agent=agent)
    assert envelope.spent_today == 0
    assert envelope.spent_this_month == 0


@pytest.mark.django_db
def test_reject_unknown_vendor():
    agent, client = helper()
    envelope = BudgetEnvelope.objects.get(agent=agent)
    envelope.vendor_allowlist = ["aws", "gcp"]
    envelope.save(update_fields=["vendor_allowlist"])
    response = client.post("/policy/process_spend_request/",
        data={"amount": 10_000, "vendor": "sketchy-vendor"}, format="json")
    assert response.status_code == 403


@pytest.mark.django_db
def test_escalate_above_threshold():
    agent, client = helper()
    response = client.post("/policy/process_spend_request/",
        data={"amount": 60_000, "vendor": "aws"}, format="json")
    assert response.status_code == 202


@pytest.mark.django_db
def test_auth_returns():
    client = APIClient()  # no credentials
    response = client.post("/policy/process_spend_request/",
        data={"amount": 10_000, "vendor": "aws"}, format="json")
    assert response.status_code in (401, 403)
    
    
@pytest.mark.django_db
def test_approve_escalated_request():
    agent, client = helper()
    # escalate
    response = client.post("/policy/process_spend_request/",
        data={"amount": 60_000, "vendor": "aws"}, format="json")
    assert response.status_code == 202
    # get approval id
    from policy.models import ApprovalRequest
    approval = ApprovalRequest.objects.last()
    # approve it
    admin_client = APIClient()
    response = admin_client.post(f"/policy/process_approval_decision/{approval.id}/decide/",
        data={"decision": "approve", "approver_name": "manager"}, format="json")
    assert response.status_code == 200
    # verify budget deducted
    envelope = BudgetEnvelope.objects.get(agent=agent)
    assert envelope.spent_today == 60_000
    
    
@pytest.mark.django_db
def test_deny_escalated_request():
    agent, client = helper()
    response = client.post("/policy/process_spend_request/",
        data={"amount": 60_000, "vendor": "aws"}, format="json")
    approval = ApprovalRequest.objects.last()
    admin_client = APIClient()
    response = admin_client.post(f"/policy/process_approval_decision/{approval.id}/decide/",
        data={"decision": "deny", "approver_name": "manager"}, format="json")
    assert response.status_code == 200
    envelope = BudgetEnvelope.objects.get(agent=agent)
    assert envelope.spent_today == 0


@pytest.mark.django_db
def test_already_decided_returns_409():
    agent, client = helper()
    response = client.post("/policy/process_spend_request/",
        data={"amount": 60_000, "vendor": "aws"}, format="json")
    approval = ApprovalRequest.objects.last()
    admin_client = APIClient()
    # first approve
    admin_client.post(f"/policy/process_approval_decision/{approval.id}/decide/",
        data={"decision": "approve", "approver_name": "manager"}, format="json")
    # second attempt
    response = admin_client.post(f"/policy/process_approval_decision/{approval.id}/decide/",
        data={"decision": "approve", "approver_name": "manager"}, format="json")
    assert response.status_code == 409


@pytest.mark.django_db
def test_expired_approval_returns_410():
    agent, client = helper()
    response = client.post("/policy/process_spend_request/",
        data={"amount": 60_000, "vendor": "aws"}, format="json")
    approval = ApprovalRequest.objects.last()
    # force expiry
    approval.expires_at = timezone.now() - timedelta(minutes=1)
    approval.save(update_fields=["expires_at"])
    admin_client = APIClient()
    response = admin_client.post(f"/policy/process_approval_decision/{approval.id}/decide/",
        data={"decision": "approve", "approver_name": "manager"}, format="json")
    assert response.status_code == 410