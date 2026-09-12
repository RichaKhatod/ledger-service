from django.db import models
from agents.models import *
from ledger.models import Transaction

class SpendRequestStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    ESCALATED = "escalated", "Escalated"
    EXPIRED = "expired", "Expired"

class SpendRequest(models.Model):
    agent = models.ForeignKey(Agent, on_delete=models.PROTECT, related_name="agent")
    idempotency_key = models.CharField(max_length=200, null=True, blank=True)
    amount = models.BigIntegerField()
    vendor = models.CharField(max_length=200)
    purpose = models.TextField()
    status = models.CharField(max_length=200, choices=SpendRequestStatus.choices, default=SpendRequestStatus.PENDING)
    policy_decision_reason = models.TextField(blank=True, default="")
    transaction = models.ForeignKey(Transaction, on_delete=models.PROTECT, null=True, blank=True, related_name="spend_requests")
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)