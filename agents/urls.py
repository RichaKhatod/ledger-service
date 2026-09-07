from django.urls import path, re_path
from agents import views

urlpatterns = [
    re_path(r'^create_with_key/$', views.create_with_key),
    re_path(r'^freeze_agent/(?P<agent_id>\d+)/$', views.freeze_agent),
    re_path(r'^unfreeze_agent/(?P<agent_id>\d+)/$', views.unfreeze_agent),    
]