from django.urls import path, re_path
from audit import views

urlpatterns = [
    re_path(r'^get_anomaly_alerts/$', views.get_anomaly_alerts),
]