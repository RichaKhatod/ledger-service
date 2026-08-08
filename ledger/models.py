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