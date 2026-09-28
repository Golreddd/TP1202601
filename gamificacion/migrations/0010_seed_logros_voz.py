from django.db import migrations


# Logros del asistente de voz (ver financiero/voz.py, financiero/voz_servicios.py
# y gamificacion/services.py::verificar_y_otorgar_logros, contexto='voz').
LOGROS = [
    {
        'codigo': 'MANOS_LIBRES',
        'nombre': 'Manos Libres',
        'descripcion': 'Registraste tu primer ingreso o gasto usando el asistente de voz.',
        'icono': '🎙️',
        'puntos': 20,
        'orden': 28,
    },
    {
        'codigo': 'ASISTENTE_FIEL',
        'nombre': 'Asistente Fiel',
        'descripcion': 'Registraste 10 ingresos o gastos usando el asistente de voz.',
        'icono': '🗣️',
        'puntos': 60,
        'orden': 29,
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
        ('gamificacion', '0009_seed_logros_ampliados'),
    ]

    operations = [
        migrations.RunPython(seed_logros, reverse_code=remove_logros),
    ]
