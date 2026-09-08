from django.db import migrations


CHECKOUT_METHODS = (
    ("orange_money", "Mobile Money"),
    ("wave", "Wave"),
    ("card", "Carte bancaire"),
)


def ensure_checkout_methods(apps, schema_editor):
    PaymentMethod = apps.get_model("payments", "PaymentMethod")
    for code, name in CHECKOUT_METHODS:
        obj, created = PaymentMethod.objects.get_or_create(
            code=code,
            defaults={"name": name, "is_active": True},
        )
        if not created:
            updates = []
            if not obj.is_active:
                obj.is_active = True
                updates.append("is_active")
            if obj.name != name:
                obj.name = name
                updates.append("name")
            if updates:
                obj.save(update_fields=updates)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0006_alter_paymentmethod_options_and_more"),
    ]

    operations = [
        migrations.RunPython(ensure_checkout_methods, noop_reverse),
    ]
