from celery import shared_task
from django.utils import timezone
from policy.models import ApprovalRequest
from budgets.models import BudgetEnvelope
from policy.models import SpendRequest
from audit.models import AnomalyAlert
from django.db.models import Sum, Count
from datetime import timedelta


@shared_task
def expire_pending_approvals():
    expired = ApprovalRequest.objects.filter(
        decision = "pending",
        expires_at__lt = timezone.now(),
    )
    for approval in expired:
        approval.decision="denied"
        approval.decided_at=timezone.now()
        approval.save(update_fields=["decision", "decided_at"])
        approval.spend_request.status = "expired"
        approval.spend_request.save(update_fields=["status"])
        
        
@shared_task
def scan_for_anomalies():
    fifteen_min_ago = timezone.now() - timedelta(minutes=15)

    # find agents with recent approved spends
    recent = SpendRequest.objects.filter(
        status="approved",
        created_at__gte=fifteen_min_ago,
    ).values("agent_id").annotate(
        total=Sum("amount"),
        count=Count("id"),
    )

    for entry in recent:
        agent_id = entry["agent_id"]
        try:
            envelope = BudgetEnvelope.objects.get(agent_id=agent_id)
        except BudgetEnvelope.DoesNotExist:
            continue

        # flag if spent > 80% of daily limit in 15 minutes
        if entry["total"] > envelope.daily_limit * 0.8:
            AnomalyAlert.objects.create(
                agent_id=agent_id,
                alert_type="rapid_spending",
                details={
                    "total_15min": entry["total"],
                    "txn_count": entry["count"],
                    "daily_limit": envelope.daily_limit,
                },
            )