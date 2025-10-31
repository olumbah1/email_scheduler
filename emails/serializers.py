from rest_framework import serializers
from .models import ScheduledEmail

class ScheduledEmailSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScheduledEmail
        fields = ['id', 'recipient_email', 'subject', 'content', 'email_header', 
                  'scheduled_time', 'recurrence_type', 'is_active', 'created_at', 'last_sent']
        read_only_fields = ['created_at', 'last_sent']