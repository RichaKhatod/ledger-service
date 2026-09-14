from django.test import TestCase
from agents.utils import *
from budgets.models import *
from ledger.models import *
from rest_framework.test import APIClient
import pytest
from policy.tests import helper


@pytest.mark.django_db
def test_approve_logs_event():
    agent, client = helper()
    client.post("/policy/process_spend_request/",
        data={"amount": 10_000, "vendor": "aws"}, format="json")
    from audit.models import AuditEvent
    events = AuditEvent.objects.filter(event_type="spend_approved")
    assert events.count() == 1

@pytest.mark.django_db
def test_reject_logs_event():
    agent, client = helper()
    client.post("/policy/process_spend_request/",
        data={"amount": 200_000, "vendor": "aws"}, format="json")
    from audit.models import AuditEvent
    events = AuditEvent.objects.filter(event_type="spend_rejected")
    assert events.count() == 1

@pytest.mark.django_db
def test_escalate_logs_event():
    agent, client = helper()
    client.post("/policy/process_spend_request/",
        data={"amount": 60_000, "vendor": "aws"}, format="json")
    from audit.models import AuditEvent
    events = AuditEvent.objects.filter(event_type="spend_escalated")
    assert events.count() == 1