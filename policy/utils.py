from .models import *
from django.db import transaction
from budgets.models import BudgetEnvelope
from ledger.utils import create_transaction
from .engine import *
from ledger.models import Account
from audit.logger import *
from django.utils import timezone
from datetime import timedelta
from django.db.models import Sum
from audit.models import *


def process_spend_request_util(agent_id, amount, vendor, purpose="", metadata=None):
	spend_request = SpendRequest.objects.create(
						agent_id=agent_id,
						amount=amount,
						vendor=vendor,
						purpose=purpose,
						metadata=metadata or {}
					)
	with transaction.atomic():
		envelope = BudgetEnvelope.objects.select_for_update().get(agent_id=agent_id)
			
		result = evaluate(amount, vendor, envelope)
  
		if result.decision==Decision.REJECT:
			spend_request.status = "rejected"
			spend_request.policy_decision_reason = result.reason
			spend_request.save(update_fields=["status", "policy_decision_reason"])
			log_event(event_type="spend_rejected", agent=spend_request.agent, spend_request=spend_request, payload={"reason": result.reason})
			return ("Request rejected", {"reason":result.reason}, 403)

		# velocity check — can upgrade APPROVE to ESCALATE
		anomaly = velocity_checks_util(agent_id, amount, vendor, envelope)
		if anomaly:
			AnomalyAlert.objects.create(
				agent_id=agent_id, alert_type=anomaly,
				details={"amount": amount, "vendor": vendor},
			)
			spend_request.status = "escalated"
			spend_request.policy_decision_reason = f"Anomaly: {anomaly}"
			spend_request.save(update_fields=["status", "policy_decision_reason"])
			ApprovalRequest.objects.create(
				spend_request=spend_request,
				expires_at=timezone.now() + timedelta(minutes=30),
			)
			log_event("spend_escalated", agent=spend_request.agent, spend_request=spend_request,
					payload={"anomaly": anomaly})
			return ("Anomaly detected — escalated", {"alert_type": anomaly}, 202)

		if result.decision==Decision.ESCALATE:
					spend_request.status = "escalated"
					spend_request.policy_decision_reason = result.reason
					spend_request.save(update_fields=["status", "policy_decision_reason"])
					ApprovalRequest.objects.create(
						spend_request=spend_request,
						expires_at=timezone.now() + timedelta(minutes=30),
					)
					log_event(event_type="spend_escalated", agent=spend_request.agent, spend_request=spend_request, payload={"amount": amount, "reason": result.reason})
					return ("Request escalated", {"spend_request_id": spend_request.id}, 202)
  
		if result.decision==Decision.APPROVE:
			#deduct budget
			envelope.spent_today += amount
			envelope.spent_this_month += amount
			envelope.save(update_fields=["spent_today", "spent_this_month"])
			# create ledger entries
			try:
				expense_account = Account.objects.get(name="Agent Expense")
				vendor_payable = Account.objects.get(name="Vendor Payable")
				txn = create_transaction(
					kind="agent_spend",
					entries=[
						{"account_id": expense_account.id, "amount": amount},
						{"account_id": vendor_payable.id, "amount": -amount},
					],
					metadata={
						"agent_id": agent_id,
						"vendor": vendor,
						"spend_request_id": spend_request.id,
					},
				)
				spend_request.transaction = txn
			except Account.DoesNotExist:
				pass  # ledger accounts not seeded yet — still approve
			spend_request.status = "approved"
			spend_request.save(update_fields=["status", "transaction"])
			log_event(event_type="spend_approved", agent=spend_request.agent, spend_request=spend_request, payload={"amount": amount, "vendor": vendor})
			return ("Approved", {"spend_request_id": spend_request.id}, 201)


def process_approval_decision_util(approval_id, decision, approver_name):
	with transaction.atomic():
		approval = ApprovalRequest.objects.select_for_update().get(id=approval_id)
		
		if approval.decision != "pending":
			return ("approval decision already made", {}, 409)
		
		if timezone.now() > approval.expires_at:
			approval.decision = "denied"
			approval.decided_at = timezone.now()
			approval.save(update_fields=["decision", "decided_at"])
			return ("Approval request denied", {"approval_id":approval_id}, 410)

		spend_request = approval.spend_request

		if decision == "approve":

			envelope = BudgetEnvelope.objects.select_for_update().get(agent_id=spend_request.agent_id)
   
			if envelope.spent_today + spend_request.amount > envelope.daily_limit:
				approval.decision = "denied"
				approval.approver_name = approver_name
				approval.decided_at = timezone.now()
				approval.save(update_fields=["decision", "approver_name", "decided_at"])
				spend_request.status = "rejected"
				spend_request.save(update_fields=["status"])
				return ("budget exhausted", {}, 403)
			
			#deduct budget
			envelope.spent_today += spend_request.amount
			envelope.spent_this_month += spend_request.amount
			envelope.save(update_fields=["spent_today", "spent_this_month"])
			
			try:
				expense_account = Account.objects.get(name="Agent Expense")
				vendor_payable = Account.objects.get(name="Vendor Payable")
				txn = create_transaction(
					kind="agent_spend",
					entries=[
						{"account_id": expense_account.id, "amount": spend_request.amount},
						{"account_id": vendor_payable.id, "amount": -spend_request.amount},
					],
					metadata={
						"agent_id": spend_request.agent_id,
						"vendor": spend_request.vendor,
						"spend_request_id": spend_request.id,
					},
				)
				spend_request.transaction = txn
			except Account.DoesNotExist:
				pass  # ledger accounts not seeded yet — still approve
			
			approval.decision = "approved"
			approval.approver_name = approver_name
			approval.decided_at = timezone.now()
			approval.save(update_fields=["decision", "approver_name", "decided_at"])

			spend_request.status = "approved"
			spend_request.save(update_fields=["status", "transaction"])
			log_event("approval_granted", agent=spend_request.agent, spend_request=spend_request,
                      payload={"approver": approver_name})
			return ("Approved", {"spend_request_id": spend_request.id}, 200)

		elif decision == "deny":
			approval.decision = "denied"
			approval.approver_name = approver_name
			approval.decided_at = timezone.now()
			approval.save(update_fields=["decision", "approver_name", "decided_at"])

			spend_request.status = "rejected"
			spend_request.save(update_fields=["status"])
			log_event("approval_denied", agent=spend_request.agent, spend_request=spend_request,
					payload={"approver": approver_name})
			return ("Denied", {}, 200)


def velocity_checks_util(agent_id, amount, vendor, envelope):
    # check 1: spend in last hour > 3x hourly average
    one_hour_ago = timezone.now() - timedelta(hours=1)
    
    recent_spend_request = SpendRequest.objects.filter(
        agent_id=agent_id,
        status="approved",
        created_at__gte=one_hour_ago
    ).aggregate(total=Sum("amount"))["total"] or 0
    
     # check 2: single request > 50% of daily limit
    high_single_spend = amount > (envelope.daily_limit * 0.5)
    
    # check 3: vendor never used before + high amount
    vendor_used = SpendRequest.objects.filter(
        agent_id=agent_id, vendor=vendor, status="approved"
    ).exists()
    
    new_vendor_high = (not vendor_used) and (amount > envelope.auto_approve_threshold * 0.25)
    
    if recent_spend_request + amount > envelope.daily_limit * 3:
        return "velocity_spike"
    if high_single_spend:
        return "high_single_transaction"
    if new_vendor_high:
        return "new_vendor_high_amount"
    
    return None