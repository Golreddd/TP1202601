from django.contrib.auth.models import AbstractUser
from django.db import models


class Rol(models.Model):
    """
    Catálogo de roles del sistema SIGAMOS (RBAC).
    Tabla de referencia con exactamente 2 registros: USUARIO y ADMIN.
    Un usuario tiene exactamente un rol (FK directa, no ManyToMany).
    """
    USUARIO = 'USUARIO'
    ADMIN   = 'ADMIN'

    NOMBRE_CHOICES = [
        (USUARIO, 'Usuario'),
        (ADMIN,   'Administrador'),
    ]

    nombre      = models.CharField(
        max_length=20,
        unique=True,
        choices=NOMBRE_CHOICES,
        verbose_name='Nombre del rol',
    )
    descripcion = models.CharField(max_length=200, verbose_name='Descripción')

    class Meta:
        verbose_name        = 'Rol'
        verbose_name_plural = 'Roles'
        ordering            = ['nombre']

    def __str__(self):
        return self.get_nombre_display()

    @property
    def es_admin(self):
        return self.nombre == self.ADMIN


class Usuario(AbstractUser):
    """
    Usuario del sistema SIGAMOS.

    - Login por email  (USERNAME_FIELD = 'email').
    - Rol asignado via FK a Rol (no boolean is_staff directo).
    - is_staff se sincroniza automáticamente con el rol al hacer save().
    - Campos de perfil financiero integrados directamente (sin tabla 1:1 extra):
        edad, nivel_educ, miembros_hogar  → requeridos por src/predict.py
        telefono, ciudad                  → opcionales, solo UI
    """
    NIVEL_EDUC_CHOICES = [
        (1, 'Sin educación formal'),
        (2, 'Primaria completa'),
        (3, 'Secundaria completa'),
        (4, 'Técnico / Instituto Superior'),
        (5, 'Universitario completo'),
        (6, 'Posgrado'),
    ]

    # ── Identificación ────────────────────────────────────────────────────────
    email    = models.EmailField(unique=True, verbose_name='Correo electrónico')
    nickname = models.CharField(
        max_length=30,
        unique=True,
        verbose_name='Nickname',
        help_text='Nombre de usuario visible. Máx 30 caracteres.',
    )

    # ── Control de acceso ─────────────────────────────────────────────────────
    rol = models.ForeignKey(
        Rol,
        on_delete=models.PROTECT,   # no se puede borrar un rol con usuarios
        null=True,
        blank=True,
        related_name='usuarios',
        verbose_name='Rol',
    )

    # ── Perfil financiero (entrada para predict.py) ───────────────────────────
    edad = models.PositiveSmallIntegerField(
        null=True, blank=True,
        verbose_name='Edad (años)',
        help_text='Requerido para el análisis ML.',
    )
    nivel_educ = models.PositiveSmallIntegerField(
        choices=NIVEL_EDUC_CHOICES,
        null=True, blank=True,
        verbose_name='Nivel educativo',
        help_text='Requerido para el análisis ML.',
    )
    miembros_hogar = models.PositiveSmallIntegerField(
        default=1,
        verbose_name='Miembros del hogar',
        help_text='Requerido para el análisis ML.',
    )

    # ── Contacto (solo UI, no usados en ML) ──────────────────────────────────
    telefono = models.CharField(max_length=20, blank=True, default='', verbose_name='Teléfono')
    ciudad   = models.CharField(max_length=100, blank=True, default='Lima', verbose_name='Ciudad')

    USERNAME_FIELD  = 'email'
    REQUIRED_FIELDS = ['username', 'nickname']

    class Meta:
        verbose_name        = 'Usuario'
        verbose_name_plural = 'Usuarios'

    def __str__(self):
        return self.nickname or self.email

    def save(self, *args, **kwargs):
        # username = nickname si no se especificó otro valor
        if not self.username:
            self.username = self.nickname
        # Sincroniza is_staff con el rol para compatibilidad con
        # @staff_member_required y el admin interno de Django
        if self.rol is not None:
            self.is_staff = self.rol.es_admin
        elif self.pk is None:
            self.is_staff = False
        super().save(*args, **kwargs)

    # ── Propiedades ───────────────────────────────────────────────────────────

    @property
    def nombre_rol(self):
        return self.rol.get_nombre_display() if self.rol else 'Sin rol'

    @property
    def es_admin(self):
        return self.rol is not None and self.rol.nombre == Rol.ADMIN

    @property
    def perfil_completo(self):
        """True si tiene los 3 campos que necesita predict.py."""
        return bool(self.edad and self.nivel_educ and self.miembros_hogar)
