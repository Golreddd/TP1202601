from django.db import migrations


# Spec §2 paso 5 (cierre de mes): logros por cumplir la meta mensual propuesta,
# otorgados por _racha_metas_mensuales_cumplidas() en gamificacion/services.py.
LOGROS = [
    {
        'codigo': 'META_MENSUAL_CUMPLIDA',
        'nombre': 'Meta del Mes',
        'descripcion': 'Cerraste un mes cumpliendo la meta de ahorro que se te propuso.',
        'icono': '✅',
        'puntos': 30,
        'orden': 13,
    },
    {
        'codigo': 'RACHA_METAS_3',
        'nombre': 'Racha de Metas',
        'descripcion': 'Cumpliste tu meta de ahorro mensual 3 meses consecutivos.',
        'icono': '🔗',
        'puntos': 80,
        'orden': 14,
    },
]


def seed_logros(apps, schema_editor):
    Logro = apps.get_model('gamificacion', 'Logro')
    for data in LOGROS:
        Logro.objects.get_or_create(codigo=data['codigo'], defaults=data)


def remove_logros(apps, schema_editor):
    Logro = apps.get_model('gamificacion', 'Logro')
    Logro.objects.filter(codigo__in=[d['codigo'] for d in LOGROS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('gamificacion', '0007_remove_orphan_logros'),
    ]

    operations = [
        migrations.RunPython(seed_logros, reverse_code=remove_logros),
    ]
