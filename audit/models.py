from django.db import models
from agents.models import *
from policy.models import *


class AuditEvent(models.Model):
    event_type = models.CharField(max_length=50)
    agent = models.ForeignKey(Agent, on_delete=models.PROTECT, null=True, blank=True, related_name="audit_events")
    spend_request = models.ForeignKey(SpendRequest, on_delete=models.PROTECT, null=True, blank=True, related_name="audit_events")
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    
    
class AnomalyAlert(models.Model):
    agent = models.ForeignKey(Agent, on_delete=models.PROTECT, related_name="anomaly_alerts")
    alert_type = models.CharField(max_length=100)
    details = models.JSONField(default=dict)
    resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)