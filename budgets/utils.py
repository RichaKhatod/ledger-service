from budgets.models import BudgetEnvelope
from agents.models import Agent
from django.db.models import Sum, Count
from django.db.models.functions import TruncDate
from policy.models import SpendRequest


def get_budget_util(agent_id):
    try:
        envelope = BudgetEnvelope.objects.get(agent_id=agent_id)
    except BudgetEnvelope.DoesNotExist:
        return ("Budget not found", {}, 404)
    
    data = {
    "agent_id": envelope.agent_id,
    "daily_limit": envelope.daily_limit,
    "monthly_limit": envelope.monthly_limit,
    "per_txn_limit": envelope.per_txn_limit,
    "auto_approve_threshold": envelope.auto_approve_threshold,
    "spent_today": envelope.spent_today,
    "spent_this_month": envelope.spent_this_month,
    "daily_remaining": envelope.daily_limit - envelope.spent_today,
    "monthly_remaining": envelope.monthly_limit - envelope.spent_this_month,
    }

    return ("budget for this agent found", data, 200)


def update_budget_util(agent_id, data):
    try:
        envelope = BudgetEnvelope.objects.get(agent_id=agent_id)
    except BudgetEnvelope.DoesNotExist:
        return ("Budget not found", {}, 404)
    
    allowed_fields = ["daily_limit",
        "monthly_limit",
        "per_txn_limit",
        "auto_approve_threshold",
        "vendor_allowlist"]
    
    update_fields = []
    
    for field in allowed_fields:
        if field in data:
            setattr(envelope, field, data[field])
            update_fields.append(field)
            
    if not update_fields:
        return ("no fields to update", {}, 400)
    
    envelope.save(update_fields=update_fields)

    return ("budgeting envelope updated", {"updated_fields": update_fields}, 200)


def get_spend_summary_util(agent_id):
    approved = SpendRequest.objects.filter(agent_id=agent_id, status="approved")
    
    by_vendor = list(
		approved.values("vendor").annotate(total=Sum("amount"), count=Count("id")).order_by("-total")
	)
    
    by_day = list(approved.annotate(day=TruncDate("created_at"))
                .values("day")
                .annotate(total=Sum("amount"), count=Count("id"))
                .order_by("-day")
                )
    
    return ("summary found", {"by_vendor": by_vendor, "by_day": by_day}, 200)