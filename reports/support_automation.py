"""Envoi des messages automatiques du chat Service client."""
from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, F, Max, Q
from django.utils import timezone

from users.roles import CLIENT_ROLES, is_app_admin

from .models import SupportAutoMessage, SupportMessage

User = get_user_model()


def _system_sender():
    """Premier compte admin utilisable comme expéditeur des messages auto."""
    for user in User.objects.order_by('pk').iterator():
        if is_app_admin(user):
            return user
    return None


def _lang_ok(language: str, preferred: str | None) -> bool:
    lang = (language or 'all').strip().lower()
    if lang in ('', 'all', '*'):
        return True
    if not preferred:
        return True
    return lang == preferred.strip().lower()


def send_first_client_message_autos(client, *, preferred_lang: str | None = None) -> int:
    """Envoie les autos « 1er message client » si c’est bien le premier message du fil."""
    prior = SupportMessage.objects.filter(client=client).count()
    # Appelé juste après création du message client → total doit être 1.
    if prior != 1:
        return 0
    sender = _system_sender()
    if sender is None:
        return 0
    qs = SupportAutoMessage.objects.filter(
        is_active=True,
        trigger=SupportAutoMessage.TRIGGER_FIRST_MESSAGE,
    )
    sent = 0
    for auto in qs:
        if not _lang_ok(auto.language, preferred_lang):
            continue
        body = (auto.body or '').strip()
        if not body:
            continue
        SupportMessage.objects.create(
            client=client,
            sender=sender,
            body=body[:4000],
            is_read=False,
        )
        sent += 1
        try:
            from notifications.utils import send_fcm_notification

            send_fcm_notification(
                client,
                'Service client Bujito',
                body[:120],
                type='support',
                reference_id=str(client.pk),
                translate=False,
            )
        except Exception:
            pass
    return sent


def _target_clients(auto: SupportAutoMessage):
    base = User.objects.filter(role__in=CLIENT_ROLES)
    if auto.target == SupportAutoMessage.TARGET_FOLLOWUP:
        return base.filter(support_followup__needs_followup=True)
    if auto.target == SupportAutoMessage.TARGET_UNREAD:
        return base.annotate(
            unread_count=Count(
                'support_threads',
                filter=Q(
                    support_threads__is_read=False,
                    support_threads__sender_id=F('id'),
                ),
                distinct=True,
            )
        ).filter(unread_count__gt=0)
    since = timezone.now() - timedelta(days=30)
    return base.annotate(last_at=Max('support_threads__created_at')).filter(
        last_at__gte=since
    )


def run_due_scheduled_auto_messages(*, force: bool = False) -> dict:
    """Envoie les messages programmés dont l’heure est atteinte (1× / jour)."""
    sender = _system_sender()
    if sender is None:
        return {'sent': 0, 'skipped': 0, 'detail': 'no_admin_sender'}

    now = timezone.localtime()
    today = now.date()
    current_time = now.time().replace(second=0, microsecond=0)
    sent = 0
    skipped = 0

    qs = SupportAutoMessage.objects.filter(
        is_active=True,
        trigger=SupportAutoMessage.TRIGGER_SCHEDULED,
    )
    for auto in qs:
        if auto.scheduled_time is None:
            skipped += 1
            continue
        sched = auto.scheduled_time.replace(second=0, microsecond=0)
        if not force and current_time < sched:
            skipped += 1
            continue
        if not force and auto.last_run_date == today:
            skipped += 1
            continue

        body = (auto.body or '').strip()
        if not body:
            skipped += 1
            continue

        clients = list(_target_clients(auto)[:80])
        for client in clients:
            already = SupportMessage.objects.filter(
                client=client,
                sender=sender,
                body=body[:4000],
                created_at__date=today,
            ).exists()
            if already:
                continue
            SupportMessage.objects.create(
                client=client,
                sender=sender,
                body=body[:4000],
                is_read=False,
            )
            sent += 1
            try:
                from notifications.utils import send_fcm_notification

                send_fcm_notification(
                    client,
                    'Service client Bujito',
                    body[:120],
                    type='support',
                    reference_id=str(client.pk),
                    translate=False,
                )
            except Exception:
                pass

        auto.last_run_date = today
        auto.save(update_fields=['last_run_date', 'updated_at'])

    return {'sent': sent, 'skipped': skipped, 'date': today.isoformat()}
