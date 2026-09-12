"""
SRS 4.11: 'Backend checks upcoming due dates. Two days before each due
date, create an in-app reminder and push notification... After the due
date and unpaid status, mark the plan overdue.' SRS 4.4/4.2: low-stock
alerts.

This module is scheduler-agnostic: call `run_daily_notification_sweep()`
from a Django management command on a daily cron / Celery beat schedule
in production.
"""
from django.utils import timezone
from django.conf import settings
from django.contrib.auth import get_user_model

from apps.core.business_rules import reminder_due, is_overdue, is_low_stock
from apps.credit.models import CreditPlan
from apps.inventory.models import Laptop
from apps.notifications.models import Notification

User = get_user_model()


def _notify_admins(type_, title, message):
    for admin_user in User.objects.filter(role=User.ADMIN, is_active=True):
        Notification.objects.create(user=admin_user, type=type_, title=title, message=message, sent_at=timezone.now())


def run_daily_notification_sweep():
    """Idempotent-ish daily sweep. In production, guard against duplicate
    notifications for the same day with a uniqueness constraint or a
    'last_notified_date' field per plan/laptop if needed."""
    today = timezone.localdate()

    # SRS 4.4/4.2/10: low stock
    for laptop in Laptop.objects.filter(is_archived=False):
        if is_low_stock(laptop.quantity) and laptop.quantity > 0:
            _notify_admins(
                Notification.LOW_STOCK,
                "Low stock alert",
                f"Low stock: {laptop.brand} {laptop.model_name} has only {laptop.quantity} unit(s) left. Restock required.",
            )

    # SRS 4.11/10: upcoming / due / overdue installment reminders
    for plan in CreditPlan.objects.filter(status=CreditPlan.ACTIVE):
        person = plan.person
        if reminder_due(plan.due_date, plan.status, as_of=today):
            _notify_admins(
                Notification.UPCOMING_PAYMENT,
                "Upcoming installment payment",
                f"{person} is expected to pay Rs. {plan.installment_amount} on {plan.due_date}.",
            )
        if plan.due_date == today:
            _notify_admins(
                Notification.PAYMENT_DUE,
                "Payment due today",
                f"Payment of Rs. {plan.installment_amount} is due today from {person}.",
            )
        if is_overdue(plan.due_date, plan.status, as_of=today):
            days_overdue = (today - plan.due_date).days
            _notify_admins(
                Notification.OVERDUE,
                "Overdue payment",
                f"Payment from {person} is overdue by {days_overdue} day(s).",
            )
