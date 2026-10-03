from celery import shared_task
from .models import ProviderRecord, Transaction, ReconciliationMismatch
import logging

logger = logging.getLogger("ledger")

@shared_task
def reconcile():
    mismatches = 0
    for record in ProviderRecord.objects.filter(transaction__isnull=True):
        ReconciliationMismatch.objects.create(
            mismatch_type="missing_in_ledger", 
            provider_ref=record.provider_ref,
            provider_amount=record.amount
        )
        mismatches+=1
        
    for record in ProviderRecord.objects.filter(transaction__isnull=False):
        ledger_amount = record.transaction.entries.filter(amount__gt=0).first().amount
        if record.amount != ledger_amount:
            ReconciliationMismatch.objects.create(
                mismatch_type="amount_mismatch",
                provider_ref=record.provider_ref,
                transaction=record.transaction,
                ledger_amount=ledger_amount,
                provider_amount=record.amount,
            )
            mismatches += 1
            
    matched_txn_ids = ProviderRecord.objects.filter(transaction__isnull=False).values_list("transaction_id", flat=True)
    for transaction in Transaction.objects.filter(kind="wallet_topup").exclude(id__in=matched_txn_ids):
        ReconciliationMismatch.objects.create(mismatch_type="missing_in_provider",
                                              transaction=transaction)
        mismatches+=1
    
    logger.info("reconciliation_complete", extra={"mismatches_found": mismatches})
    return mismatches