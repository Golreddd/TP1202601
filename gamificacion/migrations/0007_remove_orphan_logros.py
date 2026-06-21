from django.db import migrations


# Logros agregados manualmente (NO por el seed 0003/0005) que no tienen ningún
# trigger en gamificacion/services.py, por lo que nunca se desbloquean y rompen
# el conteo (14/14 imposible):
#   - PRIMER_ANALISIS : duplicado de PRIMER_ML (ambos = "primer análisis ML")
#   - RACHA_3_DIAS    : el servicio solo otorga racha >=7 y >=30, nunca >=3
# Se eliminan para dejar el catálogo en los 12 logros canónicos, todos alcanzables.
ORPHANS = ['PRIMER_ANALISIS', 'RACHA_3_DIAS']


def remove_orphans(apps, schema_editor):
    Logro = apps.get_model('gamificacion', 'Logro')
    # CASCADE elimina también cualquier LogroUsuario asociado (no debería haber,
    # porque estos logros nunca se otorgan).
    Logro.objects.filter(codigo__in=ORPHANS).delete()


def noop(apps, schema_editor):
    # Irreversible a propósito: eran cruft manual sin trigger, no se recrean.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('gamificacion', '0006_rename_logro_cluster'),
    ]

    operations = [
        migrations.RunPython(remove_orphans, reverse_code=noop),
    ]
