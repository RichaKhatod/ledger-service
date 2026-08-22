from django.urls import path, re_path
from ledger import views
from .views import AccountListCreateView

urlpatterns = [
    re_path(r'^health_point_check/$', views.health_point_check),
    path("accounts/", AccountListCreateView.as_view(), name="accounts")
]