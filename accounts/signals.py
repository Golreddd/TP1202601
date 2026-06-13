from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def inicializar_usuario(sender, instance, created, **kwargs):
    """
    Al crear un usuario nuevo asigna rol USUARIO por defecto y crea su Racha.
    PerfilFinanciero ya no existe — los campos de perfil están en el propio Usuario.
    """
    if not created:
        return

    from accounts.models import Rol

    # 1. Asignar rol USUARIO si aún no tiene rol
    if instance.rol is None:
        rol_usuario, _ = Rol.objects.get_or_create(
            nombre=Rol.USUARIO,
            defaults={'descripcion': 'Usuario normal del sistema SIGAMOS'},
        )
        # update() para no disparar signal de nuevo
        sender.objects.filter(pk=instance.pk).update(
            rol=rol_usuario,
            is_staff=False,
        )

    # 2. Crear Racha inicial
    from gamificacion.models import Racha
    Racha.objects.get_or_create(usuario=instance)
