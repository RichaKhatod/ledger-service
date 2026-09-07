from django.test import TestCase
from rest_framework.test import APIClient
from budgets.models import BudgetEnvelope
import pytest
from budgets.utils import *
from agents.utils import *

# Create your tests here.
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
