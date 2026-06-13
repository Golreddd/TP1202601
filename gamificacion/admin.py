from django.contrib import admin
from gamificacion.models import Racha, Logro, LogroUsuario


@admin.register(Racha)
class RachaAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'dias_consecutivos', 'racha_maxima', 'ultimo_registro')


@admin.register(Logro)
class LogroAdmin(admin.ModelAdmin):
    list_display = ('icono', 'nombre', 'puntos', 'orden')
    ordering = ('orden',)


@admin.register(LogroUsuario)
class LogroUsuarioAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'logro', 'obtenido_en')
    search_fields = ('usuario__nickname',)
