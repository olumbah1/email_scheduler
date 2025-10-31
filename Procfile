web: gunicorn email_scheduler.wsgi --log-file -
worker: celery -A email_scheduler worker -l info
beat: celery -A email_scheduler beat -l info