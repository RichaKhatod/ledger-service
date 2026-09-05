from rest_framework.decorators import api_view
from rest_framework.response import Response
from ledger.utils import *
from rest_framework.generics import ListCreateAPIView
from .models import Account
from .serializers import AccountSerializer
from rest_framework.views import APIView
from rest_framework import status
from .utils import wallet_topup, process_idempotent_request

@api_view(['GET'])
def health_point_check(request):
    message = health_point_check_util(request)
    return Response(({'message': message}))


class AccountListCreateView(ListCreateAPIView):
    queryset = Account.objects.all()
    serializer_class = AccountSerializer


class TransactionCreateView(APIView):
    def post(self, request):
        user_id = request.data.get("user_id")
        amount = request.data.get("amount")

        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return Response({"error":"Idempotency-Key header required"}, status=status.HTTP_400_BAD_REQUEST)
        
        payload = {"user_id": user_id, "amount": amount}
        
        def handler():
            txn = wallet_topup(user_id=user_id, amount=amount)
            return {"transaction_id": txn.id, "kind": txn.kind}
                
        try:
            response_body, created = process_idempotent_request(idempotency_key, payload, handler)
        except IdempotencyConflict as e:
            return Response({"error": str(e)}, status=409)
        except (ValueError, Account.DoesNotExist) as e:
            return Response({"error": str(e)}, status=400)
        
        status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(response_body, status=status_code)
    

class AccountBalanceView(APIView):
    def get(self, request, account_id):
        balance = get_account_balance(account_id)
        return Response({"account_id": account_id, "balance":balance}, status=status.HTTP_200_OK)