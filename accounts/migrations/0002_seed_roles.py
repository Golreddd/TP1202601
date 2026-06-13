from django.db import migrations


ROLES = [
    {
        'nombre': 'USUARIO',
        'descripcion': 'Usuario normal del sistema SIGAMOS. Accede solo a sus propios datos financieros.',
    },
    {
        'nombre': 'ADMIN',
        'descripcion': 'Administrador del sistema. Gestiona usuarios, métricas y audit log.',
    },
]


def seed_roles(apps, schema_editor):
    Rol = apps.get_model('accounts', 'Rol')
    for data in ROLES:
        Rol.objects.get_or_create(nombre=data['nombre'], defaults=data)


def remove_roles(apps, schema_editor):
    Rol = apps.get_model('accounts', 'Rol')
    Rol.objects.filter(nombre__in=[r['nombre'] for r in ROLES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_roles, reverse_code=remove_roles),
    ]
