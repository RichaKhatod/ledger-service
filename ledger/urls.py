from django.urls import path, re_path
from ledger import views

urlpatterns = [
    re_path(r'^health_point_check/$', views.health_point_check)
]