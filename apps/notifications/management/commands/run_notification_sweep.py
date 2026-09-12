"""manage.py run_notification_sweep  — schedule daily via cron/Celery beat."""
from django.core.management.base import BaseCommand
from apps.notifications.tasks import run_daily_notification_sweep


class Command(BaseCommand):
    help = "Runs the daily low-stock / installment reminder sweep (SRS 4.11)."

    def handle(self, *args, **options):
        run_daily_notification_sweep()
        self.stdout.write(self.style.SUCCESS("Notification sweep complete."))
