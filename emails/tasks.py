from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from .models import ScheduledEmail
from datetime import datetime, timedelta
from pytz import timezone as pytz_timezone

LAGOS_TZ = pytz_timezone('Africa/Lagos')

@shared_task
def send_scheduled_email(email_id):
    """Send scheduled email and reschedule if recurring"""
    try:
        email = ScheduledEmail.objects.get(id=email_id)

        if not email.is_active:
            return False

        # Build email with header
        full_content = f"{email.email_header}\n\n{email.content}"

        send_mail(
            subject=email.subject,
            message=full_content,
            from_email=settings.EMAIL_HOST_USER,
            recipient_list=[email.recipient_email],
            fail_silently=False,
        )

        email.last_sent = datetime.now(LAGOS_TZ)

        # Handle recurrence
        if email.recurrence_type != 'once':
            next_send = calculate_next_send(email.scheduled_time, email.recurrence_type)
            email.next_send = next_send

            # Reschedule task
            from . import tasks
            tasks.send_scheduled_email.apply_async(
                args=[email_id],
                eta=next_send
            )
        else:
            email.is_active = False

        email.save()
        return True

    except ScheduledEmail.DoesNotExist:
        return False


def calculate_next_send(current_time, recurrence_type):
    """Calculate next send time based on recurrence type"""
    current_time = current_time.astimezone(LAGOS_TZ)

    if recurrence_type == 'daily':
        return current_time + timedelta(days=1)
    elif recurrence_type == 'weekly':
        return current_time + timedelta(weeks=1)
    elif recurrence_type == 'monthly':
        if current_time.month == 12:
            return current_time.replace(year=current_time.year + 1, month=1)
        else:
            return current_time.replace(month=current_time.month + 1)
    elif recurrence_type == 'yearly':
        return current_time.replace(year=current_time.year + 1)
    elif recurrence_type == 'birthday':
        return current_time.replace(year=current_time.year + 1)
    elif recurrence_type == 'anniversary':
        return current_time.replace(year=current_time.year + 1)
    elif recurrence_type == 'employment':
        return current_time.replace(year=current_time.year + 1)
    else:
        return current_time