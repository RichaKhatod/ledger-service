from .models import *
from django.db import transaction
from budgets.models import BudgetEnvelope
from ledger.utils import create_transaction
from .engine import *
from ledger.models import Account

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
			return ("Approved", {"spend_request_id": spend_request.id}, 201)


		elif result.decision==Decision.REJECT:
			spend_request.status = "rejected"
			spend_request.policy_decision_reason = result.reason
			spend_request.save(update_fields=["status", "policy_decision_reason"])
			return ("Request rejected", {"reason":result.reason}, 403)

		elif result.decision==Decision.ESCALATE:
			spend_request.status = "escalated"
			spend_request.policy_decision_reason = result.reason
			spend_request.save(update_fields=["status", "policy_decision_reason"])
			return ("Request escalated", {"spend_request_id": spend_request.id}, 202)