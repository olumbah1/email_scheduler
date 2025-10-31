# Scheduled Email Agent - Telex.im Integration
A smart email scheduling bot integrated with Telex.im that lets users schedule emails with natural language commands, recurring schedules, custom headers, and friendly conversation.
# Features

Email Scheduling - Schedule emails for future delivery
Natural Language - User-friendly commands and casual conversation
Recurring Emails - Daily, weekly, monthly, yearly, birthdays, anniversaries, employment dates
Custom Headers - Personalize emails with custom headers
Timezone Support - Africa/Lagos timezone (easily configurable)
Smart Scheduling - Powered by Celery for reliable task scheduling
Email Management - List, track, and cancel scheduled emails
Conversational AI - Greetings, quotes, day check-ins, and helpful responses

# Quick Start
Prerequisites

Python 3.8+
PostgreSQL
Redis
Gmail account with App Password
Telex.im account


# Usage
Telex.im Commands
Schedule an Email
/schedule "Your message here" to recipient@email.com at 2pm with header "Subject Line"
Examples:
/schedule "Don't forget the meeting!" to john@example.com at 9am with header "Meeting Reminder"
/schedule "Happy Birthday!" to mom@example.com at 7am every birthday with header "Birthday Wishes"
/schedule "Monthly report check-in" to team@example.com at 10am monthly with header "Monthly Update"
Recurrence Options:

daily - Every day
weekly - Every week
monthly - Every month
yearly - Every year
every birthday - On birthday
every anniversary - On anniversary date
employment - Employment anniversary