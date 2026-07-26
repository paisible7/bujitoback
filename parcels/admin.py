from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.urls import path
from django.shortcuts import render, redirect
from django import forms
from .models import Parcel, Consolidation

# Import protégé pour éviter de bloquer l'admin si la lib est absente
try:
    import openpyxl
except ImportError:
    openpyxl = None

class ExcelImportForm(forms.Form):
    excel_file = forms.FileField(label=_("Fichier Excel"))

@admin.register(Parcel)
class ParcelAdmin(admin.ModelAdmin):
    list_display = (
        'tracking_number',
        'display_image',
        'client_name',
        'client_phone',
        'warehouse_number',
        'status',
        'weight_volume',
        'last_updated'
    )
    list_editable = ('status',)
    list_filter = ('status', 'warehouse_number', 'last_updated')
    search_fields = ('tracking_number', 'client_name', 'client_phone', 'warehouse_number', 'description')
    raw_id_fields = ('order',)

    change_list_template = "admin/parcels/parcel_change_list.html"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('import-excel/', self.import_excel, name='parcel-import-excel'),
        ]
        return custom_urls + urls

    def import_excel(self, request):
        if not openpyxl:
            self.message_user(request, _("Erreur : La bibliothèque 'openpyxl' n'est pas installée sur le serveur."), level=messages.ERROR)
            return redirect("..")

        if request.method == "POST":
            form = ExcelImportForm(request.POST, request.FILES)
            if form.is_valid():
                excel_file = request.FILES["excel_file"]
                try:
                    workbook = openpyxl.load_workbook(excel_file)
                    sheet = workbook.active
                    count = 0
                    for row in sheet.iter_rows(min_row=2, values_only=True):
                        if not any(row): continue

                        tracking = str(row[0]).strip() if row[0] else None
                        defaults = {
                            'client_name': str(row[1]).strip() if len(row) > 1 and row[1] else None,
                            'client_phone': str(row[2]).strip() if len(row) > 2 and row[2] else None,
                            'description': str(row[3]).strip() if len(row) > 3 and row[3] else None,
                            'current_location': str(row[4]).strip() if len(row) > 4 and row[4] else None,
                            'weight_volume': str(row[5]).strip() if len(row) > 5 and row[5] else None,
                            'warehouse_number': str(row[6]).strip() if len(row) > 6 and row[6] else None,
                        }

                        # Option A : Liaison de l'image par son nom de fichier
                        if len(row) > 7 and row[7]:
                            image_name = str(row[7]).strip()
                            if image_name:
                                defaults['image'] = f"parcels/{image_name}"

                        if tracking:
                            Parcel.objects.update_or_create(tracking_number=tracking, defaults=defaults)
                        else:
                            Parcel.objects.create(**defaults)
                        count += 1

                    self.message_user(request, _("{} colis importés avec succès.").format(count))
                    return redirect("..")
                except Exception as e:
                    self.message_user(request, _("Erreur lors de l'import : {}").format(str(e)), level=messages.ERROR)

        form = ExcelImportForm()
        payload = {"form": form, "opts": self.model._meta}
        return render(request, "admin/excel_import.html", payload)

    def display_image(self, obj):
        if obj.image:
            try:
                return format_html('<img src="{}" width="50" height="50" style="border-radius: 4px; object-fit: cover; border: 1px solid #ddd;" />', obj.image.url)
            except:
                return f"{obj.image.name}" # Affiche le nom si le fichier n'est pas encore sur le serveur
        return "-"
    display_image.short_description = _("Aperçu")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('order')

@admin.register(Consolidation)
class ConsolidationAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'status', 'request_date')
    list_filter = ('status', 'request_date')
    search_fields = ('user__email',)
    filter_horizontal = ('parcels',)
    raw_id_fields = ('user',)
