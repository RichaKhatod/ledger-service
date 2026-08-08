from django.contrib import admin
from .models import Account, Transaction, Entry


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "type", "purpose", "user_id", "currency", "created_at")
    

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("id", "idempotency_key", "kind", "reverses", "metadata", "created_at")
    

@admin.register(Entry)
class EntryAdmin(admin.ModelAdmin):
    list_display = ("id", "transaction", "account", "amount", "currency", "created_at")