from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth.models import User
from django.utils import timezone
from pytz import timezone as pytz_timezone
from datetime import datetime, timedelta
import re
import json

from .models import ScheduledEmail
from .serializers import ScheduledEmailSerializer
from .tasks import send_scheduled_email

LAGOS_TZ = pytz_timezone('Africa/Lagos')


class UserLoginView(APIView):
    """User login endpoint"""
    
    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')

        try:
            user = User.objects.get(email=email)
            if user.check_password(password):
                return Response({
                    'status': 'success',
                    'user_id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'message': 'Login successful'
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'status': 'error',
                    'message': 'Invalid credentials'
                }, status=status.HTTP_401_UNAUTHORIZED)
        except User.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'User not found'
            }, status=status.HTTP_404_NOT_FOUND)


class UserRegisterView(APIView):
    """User registration endpoint"""
    
    def post(self, request):
        email = request.data.get('email')
        username = request.data.get('username')
        password = request.data.get('password')

        if User.objects.filter(email=email).exists():
            return Response({
                'status': 'error',
                'message': 'Email already exists'
            }, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password
        )

        return Response({
            'status': 'success',
            'user_id': user.id,
            'message': 'User registered successfully'
        }, status=status.HTTP_201_CREATED)


class ParseEmailRequestView(APIView):
    """Parse natural language email requests"""

    def parse_natural_request(self, text):
        """
        Parse natural language like:
        "Send me 'Hello world' on Friday at 2pm"
        "Send 'Birthday message' to john@example.com every birthday"
        """
        result = {
            'subject': None,
            'content': None,
            'recipient_email': None,
            'scheduled_time': None,
            'recurrence_type': 'once',
            'email_header': None
        }

        # Extract content between quotes
        content_match = re.search(r"['\"](.+?)['\"]", text)
        if content_match:
            result['content'] = content_match.group(1)

        # Extract recipient email
        email_match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text)
        if email_match:
            result['recipient_email'] = email_match.group(0)

        # Extract recurrence
        recurrence_keywords = {
            'daily': 'daily',
            'every day': 'daily',
            'weekly': 'weekly',
            'every week': 'weekly',
            'monthly': 'monthly',
            'every month': 'monthly',
            'yearly': 'yearly',
            'every year': 'yearly',
            'birthday': 'birthday',
            'every birthday': 'birthday',
            'anniversary': 'anniversary',
            'every anniversary': 'anniversary',
            'employment': 'employment',
            'job anniversary': 'employment',
        }

        text_lower = text.lower()
        for keyword, recurrence in recurrence_keywords.items():
            if keyword in text_lower:
                result['recurrence_type'] = recurrence
                break

        # Simple time extraction
        time_match = re.search(r'(\d{1,2}):(\d{2})\s*(am|pm)?', text)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2))
            period = time_match.group(3)

            if period and period.lower() == 'pm' and hour != 12:
                hour += 12
            elif period and period.lower() == 'am' and hour == 12:
                hour = 0

            now = datetime.now(LAGOS_TZ)
            scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

            # If time is in past, schedule for tomorrow
            if scheduled < now:
                scheduled += timedelta(days=1)

            result['scheduled_time'] = scheduled

        # Extract subject (first few words)
        if not result['subject']:
            words = text.split()[:5]
            result['subject'] = ' '.join(words)[:255]

        return result

    def post(self, request):
        user_request = request.data.get('request_text')
        user_email = request.data.get('recipient_email')
        email_header = request.data.get('email_header', 'Scheduled Message')

        if not user_request:
            return Response({
                'status': 'error',
                'message': 'No request text provided'
            }, status=status.HTTP_400_BAD_REQUEST)

        parsed = self.parse_natural_request(user_request)
        parsed['recipient_email'] = user_email or parsed['recipient_email']
        parsed['email_header'] = email_header

        if not parsed['content']:
            return Response({
                'status': 'error',
                'message': 'Could not extract email content. Use format: Send me "Your message" on [date] at [time]'
            }, status=status.HTTP_400_BAD_REQUEST)

        if not parsed['recipient_email']:
            return Response({
                'status': 'error',
                'message': 'Recipient email required'
            }, status=status.HTTP_400_BAD_REQUEST)

        if not parsed['scheduled_time']:
            return Response({
                'status': 'error',
                'message': 'Could not parse time. Use format: 2pm, 14:00, 2:30pm'
            }, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'status': 'success',
            'parsed_data': parsed,
            'message': 'Email request parsed successfully'
        }, status=status.HTTP_200_OK)


class ScheduleEmailView(APIView):
    """Schedule an email"""

    def post(self, request):
        """Schedule an email"""
        recipient_email = request.data.get('recipient_email')
        subject = request.data.get('subject', 'Scheduled Message')
        content = request.data.get('content')
        email_header = request.data.get('email_header', 'Scheduled Message')
        scheduled_time_str = request.data.get('scheduled_time')
        recurrence_type = request.data.get('recurrence_type', 'once')

        if not all([recipient_email, content, scheduled_time_str]):
            return Response({
                'status': 'error',
                'message': 'Missing required fields: recipient_email, content, scheduled_time'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get or create user from recipient email
        user, _ = User.objects.get_or_create(
            email=recipient_email,
            defaults={'username': recipient_email.split('@')[0]}
        )

        try:
            scheduled_time = datetime.fromisoformat(scheduled_time_str)
            scheduled_time = LAGOS_TZ.localize(scheduled_time)
        except ValueError:
            return Response({
                'status': 'error',
                'message': 'Invalid datetime format. Use ISO format: 2025-11-07T14:00:00'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            email = ScheduledEmail.objects.create(
                user=user,
                recipient_email=recipient_email,
                subject=subject,
                content=content,
                email_header=email_header,
                scheduled_time=scheduled_time,
                recurrence_type=recurrence_type,
                next_send=scheduled_time
            )

            # Schedule task with Celery
            send_scheduled_email.apply_async(
                args=[email.id],
                eta=scheduled_time
            )

            return Response({
                'status': 'success',
                'email_id': email.id,
                'message': f'✅ Email scheduled for {scheduled_time.strftime("%A, %B %d at %I:%M %p %Z")}',
                'recipient': recipient_email
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({
                'status': 'error',
                'message': f'Error scheduling email: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)


class ListScheduledEmailsView(APIView):
    """List all scheduled emails"""

    def get(self, request):
        # Get recipient_email from query params or request data
        recipient_email = request.query_params.get('recipient_email') or request.data.get('recipient_email')
        
        if recipient_email:
            emails = ScheduledEmail.objects.filter(recipient_email=recipient_email, is_active=True)
        else:
            emails = ScheduledEmail.objects.filter(is_active=True)

        serializer = ScheduledEmailSerializer(emails, many=True)
        return Response({
            'status': 'success',
            'count': emails.count(),
            'emails': serializer.data
        }, status=status.HTTP_200_OK)


class CancelScheduledEmailView(APIView):
    """Cancel a scheduled email"""

    def delete(self, request, email_id):
        try:
            email = ScheduledEmail.objects.get(id=email_id)
            email.is_active = False
            email.save()
            return Response({
                'status': 'success',
                'message': f'✅ Email "{email.subject}" has been cancelled'
            }, status=status.HTTP_200_OK)
        except ScheduledEmail.DoesNotExist:
            return Response({
                'status': 'error',
                'message': '❌ Email not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                'status': 'error',
                'message': f'Error cancelling email: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)