"""
SRS 4.1 / 21 (Deployment) — non-interactive admin provisioning for hosted
environments like Render, where the build step has no terminal to answer
`createsuperuser`'s interactive prompts.

Reads DJANGO_ADMIN_USERNAME / DJANGO_ADMIN_EMAIL / DJANGO_ADMIN_PASSWORD
from the environment. Safe to run on every deploy: if a user with that
username already exists, it's left untouched rather than overwritten, so
re-deploying never resets a password someone may have since changed from
within the app.
"""
import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Creates a superuser from DJANGO_ADMIN_* environment variables, if one doesn't already exist."

    def handle(self, *args, **options):
        username = os.environ.get("DJANGO_ADMIN_USERNAME")
        email = os.environ.get("DJANGO_ADMIN_EMAIL", "")
        password = os.environ.get("DJANGO_ADMIN_PASSWORD")

        if not username or not password:
            self.stdout.write(self.style.WARNING(
                "DJANGO_ADMIN_USERNAME / DJANGO_ADMIN_PASSWORD not set — skipping admin creation."
            ))
            return

        User = get_user_model()
        if User.objects.filter(username=username).exists():
            self.stdout.write(self.style.SUCCESS(f"Admin user '{username}' already exists — skipping."))
            return

        User.objects.create_superuser(username=username, email=email, password=password)
        self.stdout.write(self.style.SUCCESS(f"Created admin user '{username}'."))
