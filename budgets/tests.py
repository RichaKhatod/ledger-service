from django.test import TestCase
from rest_framework.test import APIClient
from budgets.models import BudgetEnvelope
import pytest
from budgets.utils import *
from agents.utils import *
from ledger.models import Account


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
def test_budget_get():
	agent, raw_key = create_with_key_util("bot")
	BudgetEnvelope.objects.create(
		agent=agent, daily_limit=500_000, monthly_limit=2_000_000,
		per_txn_limit=100_000, auto_approve_threshold=50_000,
	)
	client = APIClient()
	response = client.get(f"/budgets/get_budget/{agent.id}/")
	assert response.status_code == 200
	assert response.data["data"]["daily_limit"] == 500_000
	assert response.data["data"]["daily_remaining"] == 500_000

@pytest.mark.django_db
def test_budget_patch():
	agent, raw_key = create_with_key_util("bot")
	BudgetEnvelope.objects.create(
		agent=agent, daily_limit=500_000, monthly_limit=2_000_000,
		per_txn_limit=100_000, auto_approve_threshold=50_000,
	)
	client = APIClient()
	response = client.patch(
		f"/budgets/update_budget/{agent.id}/",
		data={"daily_limit": 1_000_000},
		format="json",
	)
	assert response.status_code == 200
	envelope = BudgetEnvelope.objects.get(agent=agent)
	assert envelope.daily_limit == 1_000_000


@pytest.mark.django_db
def test_spending_summary():
    agent, client = helper()
    # create an approved spend
    client.post("/policy/process_spend_request/",
        data={"amount": 10_000, "vendor": "aws"}, format="json")
    # hit summary
    summary_client = APIClient()
    response = summary_client.get(f"/budgets/get_spend_summary/{agent.id}/")
    assert response.status_code == 200
    assert len(response.data["data"]["by_vendor"]) == 1
    assert response.data["data"]["by_vendor"][0]["vendor"] == "aws"