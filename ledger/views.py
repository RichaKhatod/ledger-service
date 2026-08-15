from rest_framework.decorators import api_view
from rest_framework.response import Response
from ledger.utils import *
from rest_framework.generics import ListCreateAPIView
from .models import Account
from .serializers import AccountSerializer

@api_view(['GET'])
def health_point_check(request):
    message = health_point_check_util(request)
    return Response(({'message': message}))


class AccountListCreateView(ListCreateAPIView):
    queryset = Account.objects.all()
    serializer_class = AccountSerializer