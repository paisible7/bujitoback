from django.contrib import admin
from .models import PaymentMethod, Payment

@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_active')
    list_filter = ('is_active',)

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('reference', 'user', 'amount', 'method', 'status', 'created_at')
    list_filter = ('status', 'method', 'created_at')
    search_fields = ('reference', 'user__email', 'external_id')
    readonly_fields = ('reference', 'created_at', 'updated_at')
    actions = ('mark_completed',)

    @admin.action(description="Confirmer les paiements sélectionnés")
    def mark_completed(self, request, queryset):
        updated = 0
        skipped = 0
        for payment in queryset.select_related('order'):
            if payment.status == 'completed':
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
