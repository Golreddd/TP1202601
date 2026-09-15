"""
Management command: backfill_validacion_ml
Registra como caso de prueba (ValidacionPrimerUso) el PRIMER análisis ML de cada
usuario que aún no tenga uno. Idempotente: los usuarios ya registrados se omiten.

Uso: python manage.py backfill_validacion_ml
"""
from django.core.management.base import BaseCommand

from accounts.models import Usuario
from panel_admin.models import ValidacionPrimerUso


class Command(BaseCommand):
    help = 'Registra el primer análisis ML de cada usuario como caso de prueba real.'

    def handle(self, *args, **options):
        creados, sin_analisis = 0, 0
        pendientes = Usuario.objects.filter(validacion_ml__isnull=True).order_by('id')
        for usuario in pendientes:
            primero = usuario.resultados_ml.order_by('creado_en').first()
            if primero is None:
                sin_analisis += 1
                continue
            obj = ValidacionPrimerUso.registrar_si_primero(primero)
            if obj:
                creados += 1
                self.stdout.write(f'  {usuario.nickname:20} {obj.periodo:%Y-%m}  '
                                  f'pred={obj.label_predicha:8} real={obj.label_real:8} -> {obj.tipo}')
        self.stdout.write(self.style.SUCCESS(
            f'Casos creados: {creados} | usuarios sin análisis ML: {sin_analisis} | '
            f'total casos en BD: {ValidacionPrimerUso.objects.count()}'
        ))
