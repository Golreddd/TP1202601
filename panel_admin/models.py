from django.db import models
from django.conf import settings


class AuditLog(models.Model):
    """
    Registro de acciones administrativas (HU0073, HU0079).
    Se crea automáticamente en cada acción del panel de administración.
    """
    ACCIONES = [
        ('LOGIN_ADMIN',        'Inicio de sesión (admin)'),
        ('LOGOUT_ADMIN',       'Cierre de sesión (admin)'),
        ('CREAR_USUARIO',      'Crear usuario'),
        ('VER_USUARIO',        'Ver detalles de usuario'),
        ('ACTIVAR_USUARIO',    'Activar cuenta de usuario'),
        ('DESACTIVAR_USUARIO', 'Desactivar cuenta de usuario'),
        ('CAMBIAR_ROL',        'Cambiar rol de usuario'),
        ('EXPORTAR_DATOS',     'Exportar datos del sistema'),
        ('VER_ESTADISTICAS',   'Ver estadísticas del sistema'),
    ]

    admin = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='acciones_admin',
        verbose_name='Administrador',
    )
    accion = models.CharField(max_length=30, choices=ACCIONES, verbose_name='Acción')
    usuario_objetivo = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='logs_recibidos',
        verbose_name='Usuario afectado',
    )
    detalle    = models.TextField(blank=True, verbose_name='Detalle')
    ip_address = models.CharField(max_length=45, null=True, blank=True, verbose_name='IP')
    fecha      = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering            = ['-fecha']
        verbose_name        = 'Registro de Auditoría'
        verbose_name_plural = 'Registros de Auditoría'

    def __str__(self):
        admin_str = self.admin.nickname if self.admin else 'Sistema'
        return f'[{self.fecha.strftime("%d/%m/%Y %H:%M")}] {admin_str}: {self.get_accion_display()}'

    @classmethod
    def registrar(cls, admin, accion, usuario_objetivo=None, detalle='', request=None):
        """Helper para crear un log desde cualquier view."""
        ip = None
        if request:
            x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
            ip = x_forwarded.split(',')[0] if x_forwarded else request.META.get('REMOTE_ADDR')
        return cls.objects.create(
            admin=admin,
            accion=accion,
            usuario_objetivo=usuario_objetivo,
            detalle=detalle,
            ip_address=ip,
        )
