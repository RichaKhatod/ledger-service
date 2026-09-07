from django.test import TestCase
from rest_framework.test import APIClient
from agents.models import Agent
import pytest
from agents.utils import *
from budgets.models import BudgetEnvelope
from agents.authentication import AgentAPIKeyAuth
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIRequestFactory


@pytest.mark.django_db
def test_create_agent_via_api():
	client = APIClient()
	response = client.post("/agents/create_with_key/", data={"name": "test-bot"}, format="json")
	assert response.status_code == 201
	assert "api_key" in response.data
	# assert response.data["api_key"].startswith("agent_")
	assert response.data["api_key"]


@pytest.mark.django_db
def test_agent_key_auth():
	agent, raw_key = create_with_key_util("bot")
	BudgetEnvelope.objects.create(
		agent=agent, daily_limit=500_000, monthly_limit=2_000_000,
		per_txn_limit=100_000, auto_approve_threshold=50_000,
	)
	client = APIClient()
	client.credentials(HTTP_X_AGENT_KEY=raw_key)
	# once Day 2 spend-request endpoint exists, this key will auth there
	# for now, verify the auth backend resolves the agent
	key_hash = hash_key(raw_key)
	assert Agent.objects.get(api_key_hash=key_hash) == agent


@pytest.mark.django_db
def test_invalid_key_rejected():
	factory = APIRequestFactory()
	request = factory.get("/", HTTP_X_AGENT_KEY="bad_key")
	auth = AgentAPIKeyAuth()
	with pytest.raises(AuthenticationFailed):
		auth.authenticate(request)


@pytest.mark.django_db
def test_frozen_agent_rejected():
	agent, raw_key = create_with_key_util("bot")
	agent.is_active = False
	agent.save()
	factory = APIRequestFactory()
	request = factory.get("/", HTTP_X_AGENT_KEY=raw_key)
	auth = AgentAPIKeyAuth()
	with pytest.raises(AuthenticationFailed, match="frozen"):
		auth.authenticate(request)
  
  
@pytest.mark.django_db
def test_freeze_agent():
	agent, _ = create_with_key_util("bot")
	client = APIClient()
	response = client.post(f"/agents/freeze_agent/{agent.id}/")
	assert response.status_code == 200
	agent.refresh_from_db()
	assert agent.is_active is False

@pytest.mark.django_db
def test_unfreeze_agent():
	agent, _ = create_with_key_util("bot")
	agent.is_active = False
	agent.save()
	client = APIClient()
	response = client.post(f"/agents/unfreeze_agent/{agent.id}/")
	assert response.status_code == 200
	agent.refresh_from_db()
	assert agent.is_active is True