from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class ScheduledEmail(models.Model):
    RECURRENCE_CHOICES = [
        ('once', 'Send Once'),
        ('daily', 'Every Day'),
        ('weekly', 'Every Week'),
        ('monthly', 'Every Month'),
        ('yearly', 'Every Year'),
        ('birthday', 'Every Birthday'),
        ('anniversary', 'Every Anniversary'),
        ('employment', 'Every Employment Anniversary'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    recipient_email = models.EmailField()
    subject = models.CharField(max_length=255)
    content = models.TextField()
    email_header = models.CharField(max_length=255, blank=True, null=True)
    scheduled_time = models.DateTimeField()
    recurrence_type = models.CharField(max_length=20, choices=RECURRENCE_CHOICES, default='once')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_sent = models.DateTimeField(null=True, blank=True)
    next_send = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.subject} - {self.user.email} - {self.scheduled_time}"

    class Meta:
        ordering = ['scheduled_time']