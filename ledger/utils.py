from django.db import transaction as db_transaction
from .models import Transaction, Entry, Account

def health_point_check_util(request):
    return "Status OK"

def create_transaction(kind, entries, idempotency_key=None, metadata=None):
    total = sum(entry["amount"] for entry in entries)
    if total != 0:
        raise ValueError(f"entries must sum to zero, got {total}")
    with db_transaction.atomic():
        transaction = Transaction.objects.create(
            kind = kind,
            idempotency_key = idempotency_key,
            metadata = metadata or {}
        )
        for entry in entries:
            Entry.objects.create(
                transaction = transaction,
                account_id = entry["account_id"],
                amount = entry["amount"],
                currency = entry.get("currency", "INR")
            )
    return transaction


def wallet_topup(user_id, amount):
    psp = Account.objects.get(name="PSP Receivable")
    wallet = Account.objects.get(user_id=user_id, purpose="wallet")
    entries = [
        {"account_id": psp.id, "amount": amount},
        {"account_id": wallet.id, "amount": -amount},
    ]
    return create_transaction(kind="wallet_topup", entries=entries)