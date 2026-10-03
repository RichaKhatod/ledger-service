from django.db import models


class AccountType(models.TextChoices):
    ASSET = "asset", "Asset"
    LIABILITY = "liability", "Liability"
    EQUITY = "equity", "Equity"
    REVENUE = "revenue", "Revenue"
    EXPENSE = "expense", "Expense"


class PurposeType(models.TextChoices):
    WALLET = "wallet", "Wallet"
    HELD_FUNDS = "held_funds", "Held funds"


class TransactionKind(models.TextChoices):
    TOPUP = "wallet_topup", "Wallet topup"
    PAYMENT = "wallet_payment", "Wallet payment"
    FEE = "fee_charge", "Fee charge"
    REFUND = "refund", "Refund"


class Account(models.Model):
    name = models.CharField(max_length=200, null=True, blank=True)
    type = models.CharField(max_length=200, choices=AccountType.choices)
    purpose = models.CharField(max_length=500, choices=PurposeType.choices, null=True)
    user_id = models.IntegerField(null=True, blank=True)
    currency = models.CharField(max_length=3)
    created_at = models.DateTimeField(auto_now_add=True)
    

class Transaction(models.Model):
    idempotency_key = models.CharField(max_length=200, null=True, blank=True)
    kind = models.CharField(max_length=200, choices=TransactionKind.choices)
    reverses = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    
class Entry(models.Model):
    transaction = models.ForeignKey(Transaction, on_delete=models.PROTECT, related_name="entries")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="entries")
    amount = models.BigIntegerField()
    currency = models.CharField(max_length=3)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        constraints = [models.CheckConstraint(check=~models.Q(amount=0), name="entry_amount_nonzero")]
        indexes = [models.Index(fields=["account"])]
        
        
class IdempotencyKey(models.Model):
    key = models.CharField(max_length=255, unique=True)
    request_hash = models.CharField(max_length=64)
    response_body = models.JSONField()
    transaction = models.ForeignKey(Transaction, on_delete=models.PROTECT, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    
class LedgerAuditEventType(models.TextChoices):
    TRANSACTION_CREATED = "transaction_created", "Transaction created"
    TRANSACTION_REVERSED = "transaction_reversed", "Transaction reversed"


class LedgerAuditEvent(models.Model):
    event_type = models.CharField(max_length=50, choices=LedgerAuditEventType.choices)
    transaction = models.ForeignKey(Transaction, on_delete=models.PROTECT, null=True, blank=True)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    
    
class WebhookNonce(models.Model):
    nonce = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    

class ProviderRecord(models.Model):
    provider_ref = models.CharField(max_length=200, unique=True)
    amount = models.BigIntegerField()
    status = models.CharField(max_length=50)
    transaction = models.ForeignKey(Transaction, on_delete=models.PROTECT, null=True, blank=True, related_name="provider_records",)
    created_at = models.DateTimeField(auto_now_add=True)
    
    
class ReconciliationMismatchEventType(models.TextChoices):
    MISSING_IN_PROVIDER = "missing_in_provider", "Missing in provider"
    MISSING_IN_LEDGER = "missing_in_ledger", "Missing in ledger"
    AMOUNT_MISMATCH = "amount_mismatch", "Amount mismatch"
    
    
class ReconciliationMismatch(models.Model):
    mismatch_type = models.CharField(max_length=50, choices=ReconciliationMismatchEventType.choices)
    provider_ref = models.CharField(max_length=200, null=True)
    transaction = models.ForeignKey(Transaction, on_delete=models.PROTECT, null=True, blank=True, related_name="reconciliation_mismatch",)
    ledger_amount = models.BigIntegerField(null=True)
    provider_amount = models.BigIntegerField(null=True)
    detected_at = models.DateTimeField(auto_now_add=True)