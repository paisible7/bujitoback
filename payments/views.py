import hmac
import hashlib
import uuid

from django.conf import settings
from django.db import transaction
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.parsers import JSONParser, FormParser, MultiPartParser
from rest_framework.response import Response
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from parcels.models import Order, ExpeditionRequest

from .models import PaymentMethod, Payment, SavedPaymentMethod
from .serializers import (
    PaymentSerializer,
    SavedPaymentMethodSerializer,
)
from .services import PaymentService


# Moyens affichés au checkout client (Mobile Money, Wave, carte).
CHECKOUT_METHOD_SPECS = (
    ("orange_money", "Mobile Money"),
    ("wave", "Wave"),
    ("card", "Carte bancaire"),
)

DEFAULT_METHOD_NAMES = {
    "orange_money": "Mobile Money",
    "mtn_momo": "MTN Mobile Money",
    "wave": "Wave",
    "moov": "Moov Money",
    "card": "Carte bancaire",
    "bank_transfer": "Virement bancaire",
}

MOBILE_MONEY_CODES = {"orange_money", "mtn_momo", "wave", "moov"}


def _format_payment_amount(amount, currency: str | None) -> str:
    """Libellé montant pour notifications (USD / Fc / £ / FCFA — jamais XOF)."""
    code = (currency or "USD").strip().upper()
    if code == "XOF":
        code = "FCFA"
    if code == "FC":
        code = "CDF"
    try:
        value = float(amount)
    except (TypeError, ValueError):
        value = 0.0
    if code == "CDF":
        return f"{value:,.0f} Fc".replace(",", " ")
    if code == "GBP":
        return f"£{value:,.2f}"
    if code == "FCFA":
        return f"{value:,.0f} FCFA".replace(",", " ")
    return f"${value:,.2f}"


def _ensure_checkout_payment_methods():
    """Crée / réactive Mobile Money, Wave et carte bancaire."""
    for code, name in CHECKOUT_METHOD_SPECS:
        obj, created = PaymentMethod.objects.get_or_create(
            code=code,
            defaults={"name": name, "is_active": True},
        )
        updates = []
        if not obj.is_active:
            obj.is_active = True
            updates.append("is_active")
        if obj.name != name:
            obj.name = name
            updates.append("name")
        if updates:
            obj.save(update_fields=updates)


def _available_method_codes():
    _ensure_checkout_payment_methods()
    codes = list(
        PaymentMethod.objects.filter(is_active=True)
        .values_list("code", flat=True)
    )
    # Ordre stable pour le checkout : Mobile Money → Wave → carte, puis le reste.
    preferred = [c for c, _ in CHECKOUT_METHOD_SPECS]
    ordered = [c for c in preferred if c in codes]
    ordered.extend(c for c in codes if c not in ordered)
    return ordered


def _ensure_method(code: str) -> PaymentMethod:
    # Keep DB flexible: if not pre-seeded, create on demand (dev-friendly).
    obj, _ = PaymentMethod.objects.get_or_create(
        code=code,
        defaults={
            "name": DEFAULT_METHOD_NAMES.get(code, code),
            "is_active": True,
        },
    )
    if not obj.is_active:
        obj.is_active = True
        obj.save(update_fields=["is_active"])
    return obj


def _mock_ussd_code(method_code: str, phone_number: str) -> str:
    digits = "".join(ch for ch in (phone_number or "") if ch.isdigit()) or "0000"
    prefixes = {
        "orange_money": "*144*",
        "mtn_momo": "*105*",
        "wave": "*145*",
        "moov": "*155*",
    }
    prefix = prefixes.get(method_code, "*144*")
    return f"{prefix}{digits}#"


def _verify_webhook_signature(request) -> bool:
    """
    Generic HMAC-SHA256 verification.
    Provider-specific signature rules may differ, but this gives a safe baseline.
    """
    secret = getattr(settings, "PAYMENT_WEBHOOK_SECRET", "") or ""
    secret = secret.strip()
    if not secret:
        # Autorisé uniquement en développement. En production, un webhook
        # non signé ne doit jamais pouvoir confirmer un paiement.
        return bool(settings.DEBUG)

    sig = (
        request.headers.get("X-Payment-Signature")
        or request.headers.get("X-Signature")
        or request.headers.get("X-Hub-Signature-256")
        or ""
    ).strip()
    if not sig:
        return False

    if sig.startswith("sha256="):
        sig = sig[len("sha256=") :]

    mac = hmac.new(secret.encode("utf-8"), msg=request.body or b"", digestmod=hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, sig)


class SavedPaymentMethodViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SavedPaymentMethodSerializer

    def get_queryset(self):
        return SavedPaymentMethod.objects.filter(user=self.request.user)

    @action(detail=False, methods=["get"], url_path="available")
    def available(self, request):
        return Response(_available_method_codes())

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        ptype = (data.get("type") or "").strip().lower()
        phone = (data.get("phone_number") or "").strip()

        phone_required = ptype in {"orange_money", "mtn_momo", "wave", "moov"}
        if phone_required and not phone:
            return Response(
                {"message": "phone_number is required for this payment type"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Default rule: first method becomes default.
        make_default = bool(data.get("is_default"))
        if not SavedPaymentMethod.objects.filter(user=request.user).exists():
            make_default = True

        if make_default:
            SavedPaymentMethod.objects.filter(user=request.user, is_default=True).update(is_default=False)

        obj = SavedPaymentMethod.objects.create(
            user=request.user,
            type=ptype,
            label=data.get("label"),
            phone_number=phone or None,
            last_four=data.get("last_four"),
            is_default=make_default,
        )

        out = self.get_serializer(obj)
        return Response(out.data, status=status.HTTP_201_CREATED)


class PaymentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)

    def _serialize_payment(self, payment, request):
        return PaymentSerializer(payment, context={'request': request}).data

    @action(detail=False, methods=["post"])
    def initiate(self, request):
        order_id = request.data.get("order_id")
        method_code = (request.data.get("method") or "").strip().lower()
        phone_number = (request.data.get("phone_number") or "").strip()
        saved_method_id = request.data.get("saved_method_id")
        transfer_type = (request.data.get("type") or "").strip().lower()
        is_transfer = transfer_type == "money_transfer"
        is_expedition = transfer_type == "expedition"
        proof_image = request.FILES.get("proof_image") if is_transfer else None
        qr_image = request.FILES.get("qr_image") if is_transfer else None
        transfer_purpose = (request.data.get("purpose") or "").strip().lower() if is_transfer else ""
        qr_provider = (request.data.get("qr_provider") or "").strip().lower() if is_transfer else ""

        if not method_code:
            return Response({"message": "method is required"}, status=status.HTTP_400_BAD_REQUEST)

        available = set(_available_method_codes())
        if method_code not in available:
            return Response({"message": "Payment method not available"}, status=status.HTTP_400_BAD_REQUEST)

        method = _ensure_method(method_code)
        if not method.is_active:
            return Response({"message": "Payment method inactive"}, status=status.HTTP_400_BAD_REQUEST)

        order = None
        expedition = None
        amount = None
        meta = None

        transfer_currency = "FCFA"
        if is_transfer:
            try:
                amount = float(request.data.get("amount"))
            except (TypeError, ValueError):
                return Response({"message": "amount is required"}, status=status.HTTP_400_BAD_REQUEST)
            if amount <= 0:
                return Response({"message": "amount must be positive"}, status=status.HTTP_400_BAD_REQUEST)

            raw_currency = (request.data.get("currency") or "FCFA").strip().upper()
            if raw_currency == "XOF":
                raw_currency = "FCFA"
            if raw_currency == "FC":
                raw_currency = "CDF"
            if raw_currency not in {"USD", "FCFA", "CDF", "GBP"}:
                return Response(
                    {"message": "currency must be USD, FCFA, CDF or GBP"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            transfer_currency = raw_currency

            beneficiary_name = (request.data.get("beneficiary_name") or "").strip()
            beneficiary_phone = (request.data.get("beneficiary_phone") or "").strip()
            note = (request.data.get("note") or "").strip()
            if not beneficiary_name:
                return Response({"message": "beneficiary_name is required"}, status=status.HTTP_400_BAD_REQUEST)
            if not beneficiary_phone:
                return Response({"message": "beneficiary_phone is required"}, status=status.HTTP_400_BAD_REQUEST)

            if not phone_number:
                phone_number = beneficiary_phone

            if transfer_purpose and transfer_purpose not in {
                "agent_transfer",
                "alipay_recharge",
                "china_supplier",
                "other",
            }:
                return Response(
                    {"message": "purpose invalide"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            meta = {
                "type": "money_transfer",
                "beneficiary_name": beneficiary_name,
                "beneficiary_phone": beneficiary_phone,
                "note": note,
                "currency": transfer_currency,
                "purpose": transfer_purpose or "other",
            }
            if qr_provider in ("alipay", "wechat"):
                meta["qr_provider"] = qr_provider
            if qr_image is not None:
                meta["has_qr_image"] = True
        elif is_expedition:
            expedition_id = request.data.get("expedition_id")
            if not expedition_id:
                return Response(
                    {"message": "expedition_id is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                expedition = ExpeditionRequest.objects.get(
                    pk=int(expedition_id),
                    user=request.user,
                )
            except Exception:
                return Response(
                    {"message": "Expedition not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )
            if expedition.status != "awaiting_payment":
                return Response(
                    {"message": "Cette expédition n'est plus payable."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if expedition.total_due_now <= 0:
                return Response(
                    {"message": "Montant d'expédition invalide."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if expedition.payments.filter(status="completed").exists():
                return Response(
                    {"message": "Cette expédition est déjà payée."},
                    status=status.HTTP_409_CONFLICT,
                )
            amount = expedition.total_due_now
            transfer_currency = "USD"
            meta = {
                "type": "expedition",
                "expedition_id": expedition.pk,
                "mode": expedition.mode,
            }
        else:
            if not order_id:
                return Response({"message": "order_id is required"}, status=status.HTTP_400_BAD_REQUEST)
            try:
                order = Order.objects.get(pk=int(order_id), user=request.user)
            except Exception:
                return Response({"message": "Order not found"}, status=status.HTTP_404_NOT_FOUND)

            if order.status.lower() not in {"pending", "processing"}:
                return Response(
                    {"message": "Cette commande n'est plus payable."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not order.quote_ready or order.total_amount <= 0:
                return Response(
                    {"message": "Le devis n'est pas encore prêt."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if order.payments.filter(status="completed").exists():
                return Response(
                    {"message": "Cette commande est déjà payée."},
                    status=status.HTTP_409_CONFLICT,
                )
            amount = order.total_amount

        if method_code in {"orange_money", "mtn_momo", "wave", "moov"} and not phone_number:
            if saved_method_id:
                try:
                    saved = SavedPaymentMethod.objects.get(pk=int(saved_method_id), user=request.user)
                    phone_number = (saved.phone_number or "").strip()
                except Exception:
                    return Response({"message": "Invalid saved_method_id"}, status=status.HTTP_400_BAD_REQUEST)
            if not phone_number:
                return Response({"message": "phone_number is required"}, status=status.HTTP_400_BAD_REQUEST)

        simulate_card = (
            method_code == "card"
            and not is_transfer
            and (order is not None or expedition is not None)
        )

        with transaction.atomic():
            if order is not None:
                order = Order.objects.select_for_update().get(pk=order.pk)
                if order.payments.filter(status="completed").exists():
                    return Response(
                        {"message": "Cette commande est déjà payée."},
                        status=status.HTTP_409_CONFLICT,
                    )
                pending_payment = (
                    order.payments.filter(status="pending")
                    .select_for_update()
                    .first()
                )
                if pending_payment is not None:
                    if not simulate_card:
                        return Response(
                            {
                                "message": "Un paiement est déjà en attente pour cette commande.",
                            },
                            status=status.HTTP_409_CONFLICT,
                        )
                    payment = pending_payment
                    payment.method = method
                    payment.phone_number = phone_number or payment.phone_number
                else:
                    payment = Payment.objects.create(
                        user=request.user,
                        order=order,
                        amount=amount,
                        currency="USD",
                        method=method,
                        reference=f"PAY-{uuid.uuid4().hex[:10].upper()}",
                        status="pending",
                        phone_number=phone_number or None,
                        provider_raw_response=meta,
                    )
            elif expedition is not None:
                expedition = ExpeditionRequest.objects.select_for_update().get(pk=expedition.pk)
                if expedition.payments.filter(status="completed").exists():
                    return Response(
                        {"message": "Cette expédition est déjà payée."},
                        status=status.HTTP_409_CONFLICT,
                    )
                pending_payment = (
                    expedition.payments.filter(status="pending")
                    .select_for_update()
                    .first()
                )
                if pending_payment is not None:
                    if not simulate_card:
                        return Response(
                            {
                                "message": "Un paiement est déjà en attente pour cette expédition.",
                            },
                            status=status.HTTP_409_CONFLICT,
                        )
                    payment = pending_payment
                    payment.method = method
                    payment.phone_number = phone_number or payment.phone_number
                else:
                    payment = Payment.objects.create(
                        user=request.user,
                        expedition=expedition,
                        amount=amount,
                        currency="USD",
                        method=method,
                        reference=f"EXP-{uuid.uuid4().hex[:10].upper()}",
                        status="pending",
                        phone_number=phone_number or None,
                        provider_raw_response=meta,
                    )
            else:
                payment = Payment.objects.create(
                    user=request.user,
                    order=order,
                    amount=amount,
                    currency=transfer_currency if is_transfer else "USD",
                    method=method,
                    reference=f"{'TRF' if is_transfer else 'PAY'}-{uuid.uuid4().hex[:10].upper()}",
                    status="pending",
                    phone_number=phone_number or None,
                    provider_raw_response=meta,
                    proof_image=proof_image,
                    qr_image=qr_image,
                )

        ussd_code = None
        if simulate_card:
            raw = payment.provider_raw_response or {}
            if not isinstance(raw, dict):
                raw = {"previous": raw}
            raw.update({"simulated": True, "method": "card"})
            payment.status = "completed"
            payment.payment_url = None
            payment.provider_raw_response = raw
            payment.save(
                update_fields=[
                    "method",
                    "phone_number",
                    "status",
                    "payment_url",
                    "provider_raw_response",
                    "updated_at",
                ]
            )
            checkout_url = None
            message = "Paiement confirmé"
        elif method_code in MOBILE_MONEY_CODES and not is_transfer:
            # Pas de lien externe : flux in-app (USSD simulé) pour Mobile Money / Wave.
            ussd_code = _mock_ussd_code(method_code, phone_number)
            raw = payment.provider_raw_response or {}
            if not isinstance(raw, dict):
                raw = {"previous": raw}
            raw.update(
                {
                    "simulated": True,
                    "method": method_code,
                    "ussd_code": ussd_code,
                }
            )
            payment.payment_url = None
            payment.provider_raw_response = raw
            payment.save(
                update_fields=[
                    "method",
                    "phone_number",
                    "payment_url",
                    "provider_raw_response",
                    "updated_at",
                ]
            )
            checkout_url = None
            message = "Composez le code USSD pour confirmer le paiement"
        elif is_transfer:
            # Transfert d'argent = service à part : reste en attente jusqu'à confirmation admin.
            checkout_url = None
            message = "Transfert initié — en attente de confirmation"
            try:
                from notifications.utils import notify_admins, send_fcm_notification

                amount_label = _format_payment_amount(payment.amount, payment.currency)
                beneficiary = (meta or {}).get("beneficiary_name") or "—"
                notify_admins(
                    "Nouveau transfert d'argent",
                    f"{request.user.email} · {amount_label} → {beneficiary}. "
                    f"Réf. {payment.reference}. À valider dans Gestion des paiements.",
                    type="payment",
                    reference_id=payment.pk,
                    data={
                        "type": "payment",
                        "payment_id": str(payment.pk),
                        "transfer": "1",
                    },
                )
                send_fcm_notification(
                    request.user,
                    "Transfert initié",
                    f"Votre transfert de {amount_label} est en attente de validation.",
                    type="payment",
                    reference_id=payment.pk,
                    data={"type": "payment", "payment_id": str(payment.pk)},
                    translate=False,
                )
            except Exception:
                pass
        else:
            checkout_url = PaymentService.initiate_payment(payment)
            message = "Paiement initialisé"

        payment.refresh_from_db()
        tx = self._serialize_payment(payment, request)
        return Response(
            {
                "transaction": tx,
                "redirect_url": checkout_url,
                "ussd_code": ussd_code,
                "message": message,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"])
    def verify(self, request):
        reference = (request.data.get("reference") or "").strip()
        if not reference:
            return Response({"message": "reference is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            payment = Payment.objects.get(reference=reference, user=request.user)
        except Payment.DoesNotExist:
            return Response({"message": "Paiement non trouvé"}, status=status.HTTP_404_NOT_FOUND)

        return Response(
            {
                "transaction": self._serialize_payment(payment, request),
                "message": f"Statut du paiement : {payment.get_status_display()}",
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"])
    def history(self, request):
        payments = self.get_queryset().order_by("-created_at")
        serializer = PaymentSerializer(
            payments, many=True, context={'request': request}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"])
    def manage(self, request):
        from users.roles import is_app_admin

        if not is_app_admin(request.user):
            return Response(
                {"message": "Accès refusé"},
                status=status.HTTP_403_FORBIDDEN,
            )
        payments = (
            Payment.objects.select_related("user", "order", "method")
            .order_by("-created_at")
        )
        serializer = PaymentSerializer(
            payments, many=True, context={'request': request}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="set-status")
    def set_status(self, request, pk=None):
        """Admin : confirmer / rejeter un paiement ou transfert d'argent."""
        from users.roles import is_app_admin
        from notifications.utils import send_fcm_notification

        if not is_app_admin(request.user):
            return Response(
                {"message": "Accès refusé"},
                status=status.HTTP_403_FORBIDDEN,
            )

        new_status = (request.data.get("status") or "").strip().lower()
        if new_status not in {"completed", "failed", "cancelled"}:
            return Response(
                {"message": "status must be completed, failed or cancelled"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            payment = Payment.objects.select_related(
                "user", "order", "method", "expedition"
            ).get(pk=pk)
        except Payment.DoesNotExist:
            return Response(
                {"message": "Paiement non trouvé"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if payment.status not in {"pending", "processing"}:
            return Response(
                {"message": "Ce paiement ne peut plus être modifié."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Paiement commande : contrôles métier uniquement à la confirmation
        if (
            new_status == "completed"
            and payment.order_id is not None
        ):
            order = payment.order
            if (
                order is None
                or not order.quote_ready
                or order.total_amount <= 0
                or payment.amount != order.total_amount
            ):
                return Response(
                    {
                        "message": (
                            "Impossible de confirmer : devis invalide "
                            "ou montant ne correspond pas."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if new_status == "completed" and payment.expedition_id is not None:
            expedition = payment.expedition
            if (
                expedition is None
                or expedition.status != "awaiting_payment"
                or expedition.total_due_now <= 0
                or payment.amount != expedition.total_due_now
            ):
                return Response(
                    {
                        "message": (
                            "Impossible de confirmer : expédition invalide "
                            "ou montant ne correspond pas."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        payment.status = new_status
        payment.save(update_fields=["status", "updated_at"])

        meta = payment.provider_raw_response if isinstance(
            payment.provider_raw_response, dict
        ) else {}
        is_transfer = (
            meta.get("type") == "money_transfer"
            or (payment.order_id is None and (payment.reference or "").startswith("TRF"))
        )

        if is_transfer and payment.user_id:
            amount_label = _format_payment_amount(payment.amount, payment.currency)
            if new_status == "completed":
                title = "Transfert confirmé"
                body = f"Votre transfert de {amount_label} a été confirmé."
            elif new_status == "failed":
                title = "Transfert échoué"
                body = f"Votre transfert de {amount_label} a été rejeté."
            else:
                title = "Transfert annulé"
                body = f"Votre transfert de {amount_label} a été annulé."
            try:
                send_fcm_notification(
                    payment.user,
                    title,
                    body,
                    type="payment",
                    reference_id=payment.pk,
                    data={"type": "payment", "payment_id": str(payment.pk)},
                    translate=False,
                )
            except Exception:
                pass

        return Response(
            {
                "transaction": self._serialize_payment(payment, request),
                "message": f"Statut mis à jour : {payment.get_status_display()}",
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], permission_classes=[permissions.AllowAny])
    @method_decorator(csrf_exempt)
    def webhook(self, request):
        if not _verify_webhook_signature(request):
            return Response({"message": "Invalid signature"}, status=status.HTTP_401_UNAUTHORIZED)

        data = request.data

        reference = (data.get("external_id") or data.get("ref_command") or data.get("reference") or "").strip()
        status_received = (data.get("status") or "").strip().lower()

        if not reference:
            return Response({"message": "Missing reference"}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            try:
                payment = Payment.objects.select_for_update().get(
                    reference=reference,
                )
            except Payment.DoesNotExist:
                return Response(
                    {"message": "Paiement non trouvé"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Map provider status to internal status.
            new_status = None
            if status_received in {"success", "completed", "paid"}:
                new_status = "completed"
            elif status_received in {"failed", "error"}:
                new_status = "failed"
            elif status_received in {"cancelled", "canceled"}:
                new_status = "cancelled"

            if new_status and payment.status != new_status:
                payment.status = new_status
                payment.updated_at = timezone.now()

            payment.provider_raw_response = data
            payment.save(
                update_fields=["status", "provider_raw_response", "updated_at"],
            )

        return Response({"status": "received"}, status=status.HTTP_200_OK)

