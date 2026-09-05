from django.test import TestCase
from rest_framework.test import APIClient
from ledger.models import Account, Entry, IdempotencyKey, Transaction
import pytest
from ledger.utils import create_transaction

@pytest.mark.django_db
def test_create_account():
    client = APIClient()
    payload = {
        "name":"Company Bank",
        "type":"asset",
        "currency":"INR"
    }
    response = client.post("/ledger/accounts/", data=payload, format="json")
    assert response.status_code == 201
    assert Account.objects.count() == 1
    assert response.data["name"] == "Company Bank"
    
    
@pytest.mark.django_db
def test_list_accounts():
    Account.objects.create(name="Test", type="asset", currency="INR")
    client = APIClient()
    response = client.get("/ledger/accounts/")
    assert response.status_code == 200
    assert len(response.data) == 1
    

@pytest.mark.django_db
def test_wallet_topup_creates_balanced_transaction():
    # arrange — create the accounts the builder needs
    Account.objects.create(name="PSP Receivable", type="asset", currency="INR")
    Account.objects.create(name=None, type="liability", purpose="wallet",
                           user_id=42, currency="INR")

    # act
    client = APIClient()
    response = client.post(
        "/ledger/transactions/",
        data={"user_id": 42, "amount": 100},
        format="json",
        headers={"Idempotency-Key": "test-key-1"}
    )

    # assert
    assert response.status_code == 201
    transaction_id = response.data["transaction_id"]
    entries = Entry.objects.filter(transaction_id=transaction_id)
    assert entries.count() == 2
    assert sum(e.amount for e in entries) == 0
    
    
@pytest.mark.django_db
def test_unbalanced_transaction_rejected():
    acc = Account.objects.create(name="Test", type="asset", currency="INR")
    with pytest.raises(ValueError):
        create_transaction(
            kind="wallet_topup",
            entries=[
                {"account_id": acc.id, "amount": 100},
                {"account_id": acc.id, "amount": -50},
            ],
        )
        

@pytest.mark.django_db(transaction=True)
def test_entries_are_immutable():
    acc = Account.objects.create(name="Test", type="asset", currency="INR")
    txn = create_transaction(
        kind="wallet_topup",
        entries=[
            {"account_id": acc.id, "amount": 100},
            {"account_id": acc.id, "amount": -100},
        ],
    )
    from django.db.utils import InternalError, ProgrammingError
    with pytest.raises((InternalError, ProgrammingError)):
        Entry.objects.filter(transaction=txn).update(amount=0)
        
        
@pytest.mark.django_db
def test_account_balance():
    # arrange: two accounts, move 100 between them
    a = Account.objects.create(name="A", type="asset", currency="INR")
    b = Account.objects.create(name="B", type="asset", currency="INR")
    create_transaction(kind="wallet_topup", entries=[
        {"account_id": a.id, "amount": 100},
        {"account_id": b.id, "amount": -100},
    ])
    # act
    client = APIClient()
    response = client.get(f"/ledger/accounts/{a.id}/balance/")
    # assert
    assert response.status_code == 200
    assert response.data["balance"] == 100
    
    
@pytest.mark.django_db
def test_empty_account_balance():
    acc = Account.objects.create(name="Empty", type="asset", currency="INR")
    client = APIClient()
    response = client.get(f"/ledger/accounts/{acc.id}/balance/")
    assert response.status_code == 200
    assert response.data["balance"] == 0
    
    
@pytest.mark.django_db
def test_first_request_create():
    Account.objects.create(name="PSP Receivable", type="asset", currency="INR")
    Account.objects.create(name=None, type="liability", purpose="wallet",
                           user_id=42, currency="INR")
    client = APIClient()
    response = client.post("/ledger/transactions/", data={"user_id": 42, "amount": 100},format="json",
            headers={"Idempotency-Key": "abc123"})
    assert response.status_code == 201
    assert Transaction.objects.count() == 1
    
    
@pytest.mark.django_db
def test_retry_request():
    Account.objects.create(name="PSP Receivable", type="asset", currency="INR")
    Account.objects.create(name=None, type="liability", purpose="wallet",
                           user_id=42, currency="INR")
    client = APIClient()
    response1 = client.post("/ledger/transactions/", data={"user_id": 42, "amount": 100},format="json",
            headers={"Idempotency-Key": "abc123"})
    assert response1.status_code == 201
    response2 = client.post("/ledger/transactions/",data={"user_id": 42, "amount": 100},format="json",
        headers={"Idempotency-Key": "abc123"},)

    assert response2.status_code == 200
    assert Transaction.objects.count() == 1
    

@pytest.mark.django_db
def test_conflict_request():
    Account.objects.create(name="PSP Receivable", type="asset", currency="INR")
    Account.objects.create(name=None, type="liability", purpose="wallet",
                           user_id=42, currency="INR")
    client = APIClient()
    response1 = client.post("/ledger/transactions/", data={"user_id": 42, "amount": 100},format="json",
                headers={"Idempotency-Key": "abc123"})
    assert response1.status_code == 201
    
    response2 = client.post("/ledger/transactions/", data={"user_id": 42, "amount": 200},format="json",
            headers={"Idempotency-Key": "abc123"})
    assert response2.status_code == 409
    assert Transaction.objects.count() == 1