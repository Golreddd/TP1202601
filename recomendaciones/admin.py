from django.contrib import admin
from recomendaciones.models import MetaMensual, MetaLargoPlazo, ResultadoML


@admin.register(MetaMensual)
class MetaMensualAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'periodo', 'monto')
    search_fields = ('usuario__nickname',)


@admin.register(MetaLargoPlazo)
class MetaLargoPlazoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'usuario', 'monto_objetivo', 'monto_actual', 'porcentaje', 'activa')
    search_fields = ('nombre', 'usuario__nickname')


@admin.register(ResultadoML)
class ResultadoMLAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'label_predicha', 'prob_ahorra', 'ahorro_actual', 'necesita_recortar', 'confianza', 'creado_en')
    list_filter = ('label_predicha',)
    readonly_fields = ('creado_en',)
