from django.contrib import admin
from .models import PaymentMethod, Payment


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_active')
    list_filter = ('is_active',)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('reference', 'user', 'amount', 'currency', 'method', 'status', 'created_at')
    list_filter = ('status', 'method', 'created_at')
    search_fields = ('reference', 'user__email', 'external_id')
    readonly_fields = ('reference', 'created_at', 'updated_at')
    actions = ('mark_completed', 'mark_failed')

    def _is_transfer(self, payment):
        raw = payment.provider_raw_response
        if isinstance(raw, dict) and raw.get('type') == 'money_transfer':
            return True
        ref = payment.reference or ''
        return payment.order_id is None and ref.startswith('TRF')

    @admin.action(description="Confirmer les paiements / transferts sélectionnés")
    def mark_completed(self, request, queryset):
        updated = 0
        skipped = 0
        for payment in queryset.select_related('order'):
            if payment.status == 'completed':
                continue
            if payment.status not in {'pending', 'processing'}:
                skipped += 1
                continue

            if self._is_transfer(payment) or payment.order_id is None:
                payment.status = 'completed'
                payment.save(update_fields=['status', 'updated_at'])
                updated += 1
                continue

            order = payment.order
            if (
                order is None
                or not order.quote_ready
                or order.total_amount <= 0
                or payment.amount != order.total_amount
            ):
                skipped += 1
                continue
            payment.status = 'completed'
            payment.save(update_fields=['status', 'updated_at'])
            updated += 1
        self.message_user(
            request,
            f"{updated} paiement(s) confirmé(s), {skipped} ignoré(s).",
        )

    @admin.action(description="Rejeter les paiements / transferts sélectionnés")
    def mark_failed(self, request, queryset):
        updated = queryset.filter(status__in=['pending', 'processing']).update(
            status='failed',
        )
        self.message_user(request, f"{updated} paiement(s) rejeté(s).")
