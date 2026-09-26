from celery import shared_task
from django.utils import timezone
from policy.models import ApprovalRequest


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