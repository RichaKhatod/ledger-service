from django.db import models
from agents.models import Agent
from django.utils import timezone


class BudgetEnvelope(models.Model):
    agent = models.OneToOneField(Agent, on_delete=models.PROTECT, related_name="budget")
    daily_limit = models.BigIntegerField()
    monthly_limit = models.BigIntegerField()
    per_txn_limit = models.BigIntegerField()
    auto_approve_threshold = models.BigIntegerField()
    spent_today = models.BigIntegerField(default=0)
    spent_this_month = models.BigIntegerField(default=0)
    vendor_allowlist = models.JSONField(default=list)
    currency = models.CharField(max_length=3)
    last_daily_reset = models.DateTimeField(default=timezone.now)
    last_monthly_reset = models.DateTimeField(default=timezone.now)