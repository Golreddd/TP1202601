from django.contrib import admin
from financiero.models import RegistroMensual


@admin.register(RegistroMensual)
class RegistroMensualAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'periodo', 'ing_total', 'gasto_total', 'ahorro_bruto')
    list_filter = ('periodo',)
    search_fields = ('usuario__email', 'usuario__nickname')
    readonly_fields = ('creado_en', 'actualizado_en')
