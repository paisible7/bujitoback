import hmac
import hashlib
import uuid

from django.conf import settings
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from parcels.models import Order

from .models import PaymentMethod, Payment, SavedPaymentMethod
from .serializers import (
    PaymentSerializer,
    SavedPaymentMethodSerializer,
)
from .services import PaymentService


def _available_method_codes():
    codes = list(
        PaymentMethod.objects.filter(is_active=True)
        .values_list("code", flat=True)
    )
    if codes:
        return codes
    # Fallback if DB is empty.
    return [
        "orange_money",
        "mtn_momo",
        "wave",
        "moov",
        "card",
        "bank_transfer",
    ]


def _ensure_method(code: str) -> PaymentMethod:
    # Keep DB flexible: if not pre-seeded, create on demand (dev-friendly).
    default_names = {
        "orange_money": "Orange Money",
        "mtn_momo": "MTN Mobile Money",
        "wave": "Wave",
        "moov": "Moov Money",
        "card": "Carte bancaire",
        "bank_transfer": "Virement bancaire",
    }
    obj, _ = PaymentMethod.objects.get_or_create(
        code=code,
        defaults={"name": default_names.get(code, code), "is_active": True},
    )
    return obj


def _verify_webhook_signature(request) -> bool:
    """
    Generic HMAC-SHA256 verification.
    Provider-specific signature rules may differ, but this gives a safe baseline.
    """
    secret = getattr(settings, "PAYMENT_WEBHOOK_SECRET", "") or ""
    secret = secret.strip()
    if not secret:
        # If no secret configured, do not block (dev), but not secure for prod.
        return True

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

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)

    @action(detail=False, methods=["post"])
    def initiate(self, request):
        order_id = request.data.get("order_id")
        method_code = (request.data.get("method") or "").strip().lower()
        phone_number = (request.data.get("phone_number") or "").strip()
        saved_method_id = request.data.get("saved_method_id")
        transfer_type = (request.data.get("type") or "").strip().lower()
        is_transfer = transfer_type == "money_transfer"

        if not method_code:
            return Response({"message": "method is required"}, status=status.HTTP_400_BAD_REQUEST)

        available = set(_available_method_codes())
        if method_code not in available:
            return Response({"message": "Payment method not available"}, status=status.HTTP_400_BAD_REQUEST)

        method = _ensure_method(method_code)
        if not method.is_active:
            return Response({"message": "Payment method inactive"}, status=status.HTTP_400_BAD_REQUEST)

        order = None
        amount = None
        meta = None

        if is_transfer:
            try:
                amount = float(request.data.get("amount"))
            except (TypeError, ValueError):
                return Response({"message": "amount is required"}, status=status.HTTP_400_BAD_REQUEST)
            if amount <= 0:
                return Response({"message": "amount must be positive"}, status=status.HTTP_400_BAD_REQUEST)

            beneficiary_name = (request.data.get("beneficiary_name") or "").strip()
            beneficiary_phone = (request.data.get("beneficiary_phone") or "").strip()
            note = (request.data.get("note") or "").strip()
            if not beneficiary_name:
                return Response({"message": "beneficiary_name is required"}, status=status.HTTP_400_BAD_REQUEST)
            if not beneficiary_phone:
                return Response({"message": "beneficiary_phone is required"}, status=status.HTTP_400_BAD_REQUEST)

            if not phone_number:
                phone_number = beneficiary_phone

            meta = {
                "type": "money_transfer",
                "beneficiary_name": beneficiary_name,
                "beneficiary_phone": beneficiary_phone,
                "note": note,
            }
        else:
            if not order_id:
                return Response({"message": "order_id is required"}, status=status.HTTP_400_BAD_REQUEST)
            try:
                order = Order.objects.get(pk=int(order_id), user=request.user)
            except Exception:
                return Response({"message": "Order not found"}, status=status.HTTP_404_NOT_FOUND)

            if order.status.lower() != "pending":
                return Response({"message": "Order is not pending"}, status=status.HTTP_400_BAD_REQUEST)
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

        payment = Payment.objects.create(
            user=request.user,
            order=order,
            amount=amount,
            currency="XOF",
            method=method,
            reference=f"{'TRF' if is_transfer else 'PAY'}-{uuid.uuid4().hex[:10].upper()}",
            status="pending",
            phone_number=phone_number or None,
            provider_raw_response=meta,
        )

        checkout_url = PaymentService.initiate_payment(payment)

        tx = PaymentSerializer(payment).data
        return Response(
            {
                "transaction": tx,
                "redirect_url": checkout_url,
                "ussd_code": None,
                "message": "Transfert initié" if is_transfer else "Paiement initialisé",
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
                "transaction": PaymentSerializer(payment).data,
                "message": f"Statut du paiement : {payment.get_status_display()}",
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"])
    def history(self, request):
        payments = self.get_queryset().order_by("-created_at")
        serializer = PaymentSerializer(payments, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

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

        try:
            payment = Payment.objects.get(reference=reference)
        except Payment.DoesNotExist:
            return Response({"message": "Paiement non trouvé"}, status=status.HTTP_404_NOT_FOUND)

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
        payment.save(update_fields=["status", "provider_raw_response", "updated_at"])

        return Response({"status": "received"}, status=status.HTTP_200_OK)

