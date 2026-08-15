from rest_framework import serializers
from .models import Account

class AccountSerializer(serializers.ModelSerializer):
    class Meta(object):
        model = Account
        fields = ['id', 'name', 'type', 'purpose', 'user_id', 'currency', 'created_at']
        read_only_fields = ['id', 'created_at']