from django.test import TestCase
from rest_framework.test import APIClient
from ledger.models import Account
import pytest

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