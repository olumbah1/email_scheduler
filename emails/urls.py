from django.urls import path
from .telex_integration import TelexWebhookView
from .views import (
    UserLoginView, UserRegisterView, ParseEmailRequestView,
    ScheduleEmailView, ListScheduledEmailsView, CancelScheduledEmailView
)

urlpatterns = [
    path('auth/register/', UserRegisterView.as_view(), name='register'),
    path('auth/login/', UserLoginView.as_view(), name='login'),
    path('email/parse/', ParseEmailRequestView.as_view(), name='parse-email'),
    path('email/schedule/', ScheduleEmailView.as_view(), name='schedule-email'),
    path('email/list/', ListScheduledEmailsView.as_view(), name='list-emails'),
    path('email/cancel/<int:email_id>/', CancelScheduledEmailView.as_view(), name='cancel-email'),
    path('telex/webhook/', TelexWebhookView.as_view(), name='telex-webhook'),
]
