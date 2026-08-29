from rest_framework.decorators import api_view
from rest_framework.response import Response
from ledger.utils import *
from rest_framework.generics import ListCreateAPIView
from .models import Account
from .serializers import AccountSerializer
from rest_framework.views import APIView
from rest_framework import status
from .utils import wallet_topup

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
        
        try:
            transaction = wallet_topup(user_id=user_id, amount=amount)
        except (ValueError, Account.DoesNotExist) as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"transaction_id": transaction.id, "kind": transaction.kind}, status=status.HTTP_201_CREATED)
    

class AccountBalanceView(APIView):
    def get(self, request, account_id):
        balance = get_account_balance(account_id)
        return Response({"account_id": account_id, "balance":balance}, status=status.HTTP_200_OK)