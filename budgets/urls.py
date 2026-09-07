from django.urls import path, re_path
from budgets import views

urlpatterns = [
    re_path(r'^get_budget/(?P<agent_id>\d+)/$', views.get_budget),
    re_path(r'^update_budget/(?P<agent_id>\d+)/$', views.update_budget)
]