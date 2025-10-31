from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth.models import User
from datetime import datetime
from pytz import timezone as pytz_timezone
import json
import re
from .models import ScheduledEmail
from .tasks import send_scheduled_email

LAGOS_TZ = pytz_timezone('Africa/Lagos')


class TelexWebhookView(APIView):
    """
    Handle incoming messages from Telex.im
    Webhook URL: https://your-domain.com/api/telex/webhook/
    """

    def verify_telex_signature(self, request):
        """Verify webhook signature from Telex.im"""
        # TODO: Implement signature verification if Telex provides
        # For now, we'll accept all requests
        return True

    def parse_user_message(self, message_text):
        """Parse user natural language input"""
        return {
            'content': message_text,
            'has_email': '@' in message_text,
        }

    def post(self, request):
        """Handle incoming Telex webhook events"""
        
        if not self.verify_telex_signature(request):
            return Response({
                'status': 'error',
                'message': 'Invalid signature'
            }, status=status.HTTP_401_UNAUTHORIZED)

        try:
            data = request.data
            
            # Extract Telex event data
            event_type = data.get('type')
            message = data.get('message', {})
            sender_id = data.get('sender_id')
            sender_email = data.get('sender_email')
            channel_id = data.get('channel_id')
            
            # Get or create user
            user, _ = User.objects.get_or_create(
                email=sender_email,
                defaults={'username': sender_email.split('@')[0]}
            )

            # Process different message types
            if event_type == 'message':
                return self.handle_message(user, message, channel_id)
            
            return Response({
                'status': 'success',
                'message': 'Event processed'
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

    def handle_message(self, user, message, channel_id):
        """Handle text message from Telex"""
        
        text = message.get('text', '').strip()
        
        if not text:
            return Response({
                'status': 'success',
                'message': 'Empty message ignored'
            }, status=status.HTTP_200_OK)

        # Command detection
        if text.lower().startswith('/schedule'):
            return self.process_schedule_command(user, text, channel_id)
        elif text.lower().startswith('/list'):
            return self.process_list_command(user, channel_id)
        elif text.lower().startswith('/cancel'):
            return self.process_cancel_command(user, text, channel_id)
        elif text.lower().startswith('/help'):
            return self.send_help_message(channel_id)
        else:
            # Natural language parsing
            return self.process_natural_language(user, text, channel_id)

    def process_schedule_command(self, user, text, channel_id):
        """
        Handle /schedule command
        Example: /schedule "Hello world" to john@example.com at 2pm tomorrow with header "Birthday"
        """
        
        # Extract components
        content_match = re.search(r'"([^"]+)"', text)
        email_match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text)
        header_match = re.search(r'header\s+["\']([^"\']+)["\']', text, re.IGNORECASE)
        
        if not content_match or not email_match:
            response_text = "❌ Invalid format. Use: /schedule \"message\" to email@domain.com at TIME with header \"Header\""
            return self.send_telex_message(channel_id, response_text)

        content = content_match.group(1)
        recipient_email = email_match.group(0)
        email_header = header_match.group(1) if header_match else "Scheduled Message"

        # Parse time
        time_match = re.search(r'(\d{1,2}):?(\d{2})?\s*(am|pm)?', text, re.IGNORECASE)
        if not time_match:
            response_text = "❌ Could not parse time. Use format: 2pm, 14:00, 2:30pm"
            return self.send_telex_message(channel_id, response_text)

        hour = int(time_match.group(1))
        minute = int(time_match.group(2) or 0)
        period = time_match.group(3)

        if period and period.lower() == 'pm' and hour != 12:
            hour += 12
        elif period and period.lower() == 'am' and hour == 12:
            hour = 0

        now = datetime.now(LAGOS_TZ)
        scheduled_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        # Check for recurrence
        recurrence_type = 'once'
        if 'daily' in text.lower():
            recurrence_type = 'daily'
        elif 'weekly' in text.lower():
            recurrence_type = 'weekly'
        elif 'monthly' in text.lower():
            recurrence_type = 'monthly'
        elif 'yearly' in text.lower():
            recurrence_type = 'yearly'
        elif 'birthday' in text.lower():
            recurrence_type = 'birthday'
        elif 'anniversary' in text.lower():
            recurrence_type = 'anniversary'

        # Create scheduled email
        email_obj = ScheduledEmail.objects.create(
            user=user,
            recipient_email=recipient_email,
            subject='Scheduled Message',
            content=content,
            email_header=email_header,
            scheduled_time=scheduled_time,
            recurrence_type=recurrence_type,
            next_send=scheduled_time
        )

        # Schedule task
        send_scheduled_email.apply_async(
            args=[email_obj.id],
            eta=scheduled_time
        )

        # Send confirmation
        recurrence_text = f" ({recurrence_type})" if recurrence_type != 'once' else ""
        confirmation = (
            f"✅ Email scheduled!\n"
            f"📧 To: {recipient_email}\n"
            f"📝 Message: {content}\n"
            f"⏰ Time: {scheduled_time.strftime('%A, %B %d at %I:%M %p %Z')}{recurrence_text}\n"
            f"🎯 Header: {email_header}"
        )
        
        return self.send_telex_message(channel_id, confirmation)

    def process_list_command(self, user, channel_id):
        """List all scheduled emails"""
        
        emails = ScheduledEmail.objects.filter(user=user, is_active=True)
        
        if not emails.exists():
            response_text = "📭 No scheduled emails yet."
            return self.send_telex_message(channel_id, response_text)

        message = "📋 Your Scheduled Emails:\n\n"
        for i, email in enumerate(emails, 1):
            next_time = email.next_send.strftime('%A, %B %d at %I:%M %p')
            message += (
                f"{i}. {email.subject}\n"
                f"   To: {email.recipient_email}\n"
                f"   Next: {next_time}\n"
                f"   Recurrence: {email.recurrence_type}\n"
                f"   ID: {email.id}\n\n"
            )

        return self.send_telex_message(channel_id, message)

    def process_cancel_command(self, user, text, channel_id):
        """
        Cancel a scheduled email
        Example: /cancel 5
        """
        
        match = re.search(r'/cancel\s+(\d+)', text)
        if not match:
            response_text = "❌ Use format: /cancel EMAIL_ID"
            return self.send_telex_message(channel_id, response_text)

        email_id = int(match.group(1))
        
        try:
            email = ScheduledEmail.objects.get(id=email_id, user=user)
            email.is_active = False
            email.save()
            
            response_text = f"✅ Email '{email.subject}' has been cancelled."
            return self.send_telex_message(channel_id, response_text)
        except ScheduledEmail.DoesNotExist:
            response_text = "❌ Email not found."
            return self.send_telex_message(channel_id, response_text)

    def send_help_message(self, channel_id):
        """Send help message"""
        
        help_text = (
            "📚 **Scheduled Email Bot Help**\n\n"
            "Commands:\n"
            "/schedule \"message\" to email@domain.com at 2pm with header \"Header\"\n"
            "/list - Show all scheduled emails\n"
            "/cancel EMAIL_ID - Cancel a scheduled email\n\n"
            "Recurrence options (add to /schedule):\n"
            "- daily, weekly, monthly, yearly\n"
            "- birthday, anniversary, employment\n\n"
            "Example:\n"
            "/schedule \"Don't forget the meeting\" to me@email.com at 9am daily with header \"Reminder\""
        )
        
        return self.send_telex_message(channel_id, help_text)

    def process_natural_language(self, user, text, channel_id):
        """
        Handle natural language input & casual conversation
        Supports both scheduling requests and friendly chat
        """
        
        text_lower = text.lower().strip()
        
        # Greeting responses
        greetings = ['hi', 'hello', 'hey', 'greetings', 'howdy']
        if any(greeting in text_lower for greeting in greetings):
            response = self.get_greeting_response(user.first_name or user.username)
            return self.send_telex_message(channel_id, response)
        
        # How are you questions
        if any(phrase in text_lower for phrase in ['how are you', 'how are u', 'how do you do', 'how you doing']):
            response = self.get_how_are_you_response()
            return self.send_telex_message(channel_id, response)
        
        # Day/week questions
        if any(phrase in text_lower for phrase in ['how is your day', 'how\'s your day', 'how is your week']):
            response = self.get_day_response()
            return self.send_telex_message(channel_id, response)
        
        # What can you do
        if any(phrase in text_lower for phrase in ['what can you do', 'what do you do', 'capabilities', 'features']):
            response = self.get_capabilities_response()
            return self.send_telex_message(channel_id, response)
        
        # Inspirational/quote requests
        if any(phrase in text_lower for phrase in ['quote', 'inspire', 'motivation', 'motivate me']):
            response = self.get_quote()
            return self.send_telex_message(channel_id, response)
        
        # Thank you responses
        if any(phrase in text_lower for phrase in ['thank you', 'thanks', 'appreciate', 'cheers']):
            response = self.get_thank_you_response()
            return self.send_telex_message(channel_id, response)
        
        # Default helpful response
        response_text = (
            "👋 Hey there! I'm your Email Scheduling Assistant.\n\n"
            "You can chat with me or schedule emails:\n"
            "• /schedule \"message\" to email@domain.com at 2pm\n"
            "• /list - See your scheduled emails\n"
            "• /help - Full command list\n\n"
            "Or just say hi! I'm here to help. 😊"
        )
        
        return self.send_telex_message(channel_id, response_text)
    
    def get_greeting_response(self, name):
        """Friendly greeting responses"""
        import random
        
        greetings = [
            f"Hey {name}! 👋 Great to see you! How can I help you schedule something today?",
            f"Hi {name}! 😊 Welcome! Ready to schedule some emails?",
            f"Hello {name}! 🎉 What can I do for you?",
            f"Yo {name}! What's up? Need to schedule something?",
            f"Hey {name}! Nice to see you around. How's it going?",
        ]
        return random.choice(greetings)
    
    def get_how_are_you_response(self):
        """Response to 'how are you'"""
        import random
        
        responses = [
            "I'm doing great, thanks for asking! 😊 I'm here and ready to help you schedule emails. How are *you* doing?",
            "Fantastic! I'm running smoothly and ready to help. How's your day treating you?",
            "I'm awesome, thanks! 🚀 Ready to schedule some emails whenever you are.",
            "Doing well! My circuits are buzzing with energy. What can I help you with?",
            "Can't complain! I'm here, energized, and ready to assist. How are YOU?",
        ]
        return random.choice(responses)
    
    def get_day_response(self):
        """Response to 'how is your day'"""
        import random
        from datetime import datetime
        
        hour = datetime.now().hour
        
        if hour < 12:
            time_context = "morning"
        elif hour < 17:
            time_context = "afternoon"
        else:
            time_context = "evening"
        
        responses = [
            f"My {time_context} is going great, thanks! 🌅 Just here helping people schedule important emails. How's yours?",
            f"Pretty good {time_context}! Just waiting to help you schedule something awesome. What's on your mind?",
            f"Can't complain! The {time_context} is young and full of possibilities. How about you?",
            f"Living my best {time_context}! 📧 Ready to help whenever you need. What's up?",
        ]
        return random.choice(responses)
    
    def get_quote(self):
        """Inspirational quotes"""
        import random
        
        quotes = [
            "✨ \"The future depends on what you do today.\" - Mahatma Gandhi",
            "💪 \"You are capable of amazing things.\" - Unknown",
            "🎯 \"Success is not final, failure is not fatal: it is the courage to continue that counts.\" - Winston Churchill",
            "🚀 \"The only way to do great work is to love what you do.\" - Steve Jobs",
            "⭐ \"Don't watch the clock; do what it does. Keep going.\" - Sam Levenson",
            "🌟 \"Believe you can and you're halfway there.\" - Theodore Roosevelt",
            "💡 \"The best time to plant a tree was 20 years ago. The second best time is now.\" - Chinese Proverb",
            "🔥 \"Your limitation—it's only your imagination.\" - Unknown",
            "🎨 \"Creativity takes courage.\" - Henri Matisse",
            "🏆 \"Excellence is not a destination; it is a continuous journey that never ends.\" - Brian Tracy",
        ]
        return random.choice(quotes)
    
    def get_thank_you_response(self):
        """Response to thanks/appreciation"""
        import random
        
        responses = [
            "You're welcome! 😊 Happy to help anytime. Need anything else?",
            "My pleasure! 🙌 That's what I'm here for. Let me know if you need more help!",
            "Anytime! 💫 Thanks for using me. Anything else I can do?",
            "Of course! 😄 That's what assistants are for. What else can I help with?",
            "Happy to help! 🎉 Feel free to come back whenever you need me!",
        ]
        return random.choice(responses)
    
    def get_capabilities_response(self):
        """Explain what the bot can do"""
        response = (
            "🤖 **Here's what I can do:**\n\n"
            "📧 **Schedule Emails** - Set reminders and messages to be sent later\n"
            "🔄 **Recurring Emails** - Daily, weekly, monthly, yearly, birthdays, anniversaries, etc.\n"
            "⏰ **Custom Headers** - Personalize your email with custom headers\n"
            "📋 **Manage Emails** - List, track, and cancel scheduled emails\n"
            "💬 **Chat** - Have a friendly conversation with me\n\n"
            "**Quick Start:**\n"
            "/schedule \"Your message\" to email@domain.com at 2pm\n"
            "/list - See all scheduled emails\n"
            "/help - Full command details\n\n"
            "What would you like to do? 😊"
        )
        return response

    def send_telex_message(self, channel_id, message_text):
        """Send message back to Telex channel"""
        
        import requests
        
        # TODO: Get your Telex.im API token from https://app.telex.im/settings
        TELEX_API_TOKEN = 'your-telex-api-token'
        TELEX_API_URL = 'https://api.telex.im/v1'

        try:
            response = requests.post(
                f'{TELEX_API_URL}/channels/{channel_id}/messages',
                headers={
                    'Authorization': f'Bearer {TELEX_API_TOKEN}',
                    'Content-Type': 'application/json'
                },
                json={
                    'text': message_text,
                    'type': 'text'
                },
                timeout=10
            )

            if response.status_code == 200:
                return Response({
                    'status': 'success',
                    'message': 'Message sent to Telex'
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'status': 'error',
                    'message': f'Failed to send message: {response.text}'
                }, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
