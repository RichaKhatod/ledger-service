from django.db import models


class Agent(models.Model):
    name = models.CharField(max_length=200, null=True, blank=True)
    api_key_hash = models.CharField(max_length=256, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)