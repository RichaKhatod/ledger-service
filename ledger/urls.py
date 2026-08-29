from django.urls import path, re_path
from ledger import views
from .views import AccountListCreateView, TransactionCreateView, AccountBalanceView

urlpatterns = [
    re_path(r'^health_point_check/$', views.health_point_check),
    path("accounts/", AccountListCreateView.as_view(), name="accounts"),
    path("transactions/", TransactionCreateView.as_view(), name="transactions"),
    path("accounts/<int:account_id>/balance/", AccountBalanceView.as_view(), name="account-balance"),
]