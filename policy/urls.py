from django.urls import path, re_path
from policy import views

urlpatterns = [
    re_path(r'^process_spend_request/', views.process_spend_request),
]