"""
Permisos personalizados para la API de SIGAMOS.
Basados en el modelo Rol (RBAC — Role-Based Access Control).
"""
from rest_framework.permissions import BasePermission


class EsAdminSigamos(BasePermission):
    """
    Solo usuarios con rol ADMIN pueden acceder.
    Compatible con @staff_member_required en vistas Django
    porque Usuario.save() sincroniza is_staff con el rol.
    """
    message = 'Acceso restringido: se requiere rol Administrador.'

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.es_admin
