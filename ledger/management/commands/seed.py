from django.core.management.base import BaseCommand
from ledger.models import Account, AccountType

class Command(BaseCommand):
    def handle(self, *args, **options):
        
        company_bank = Account.objects.get_or_create(
            name="Company Name",
            defaults={"type":AccountType.ASSET, "currency":"INR"}
        )
        
        psp_receivable = Account.objects.get_or_create(
            name="PSP Receivable",
            defaults={"type":AccountType.ASSET, "currency":"INR"}
        )
        
        fee_revenue = Account.objects.get_or_create(
            name="Fee Revenue",
            defaults={"type":AccountType.REVENUE, "currency":"INR"}
        )
        
        merchant_payable = Account.objects.get_or_create(
            name="Merchant Payable",
            defaults={"type":AccountType.LIABILITY, "currency":"INR"}
        )
        
        held_funds = Account.objects.get_or_create(
            name="Held Funds",
            defaults={"type":AccountType.LIABILITY, "currency":"INR"}
        )
        
        self.stdout.write(self.style.SUCCESS("Seeded system accounts"))