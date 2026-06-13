from django.contrib import admin
from panel_admin.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'admin', 'accion', 'usuario_objetivo', 'ip_address')
    list_filter = ('accion',)
    search_fields = ('admin__nickname', 'usuario_objetivo__nickname')
    readonly_fields = ('fecha', 'admin', 'accion', 'usuario_objetivo', 'detalle', 'ip_address')
