from django.db import transaction as db_transaction
from .models import Transaction, Entry, Account, IdempotencyKey
from django.db.models import Sum
import hashlib
import json


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


def get_account_balance(account_id):
    account_balance = Entry.objects.filter(account_id=account_id).aggregate(total=Sum("amount"))
    return account_balance["total"] or 0


def hash_payload(payload):
    # canonical JSON (sorted keys) so the same data always hashes the same
    canonical = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


class IdempotencyConflict(Exception):
    pass


def process_idempotent_request(key, payload, handler):
    request_hash = hash_payload(payload)
    
    existing_key = IdempotencyKey.objects.filter(key=key).first()
    
    if existing_key:
        if existing_key.request_hash == request_hash:
            return existing_key.response_body, False
        else:
            raise IdempotencyConflict("key reused with a different payload")
        
    result = handler()
    IdempotencyKey.objects.create(
        key=key,
        request_hash=request_hash,
        response_body=result
    )
    return result, True