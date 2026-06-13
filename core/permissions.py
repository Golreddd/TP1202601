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


class EsUsuarioNormal(BasePermission):
    """Solo usuarios con rol USUARIO (no admins)."""
    message = 'Esta acción es solo para usuarios del sistema.'

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return not request.user.es_admin


class EsDueño(BasePermission):
    """El usuario solo puede acceder a sus propios objetos."""
    message = 'No tienes permiso para acceder a este recurso.'

    def has_object_permission(self, request, view, obj):
        if hasattr(obj, 'usuario'):
            return obj.usuario == request.user
        if hasattr(obj, 'user'):
            return obj.user == request.user
        return False


class EsAdminODueño(BasePermission):
    """
    Admin puede acceder a cualquier objeto.
    Usuario normal solo puede acceder a los suyos.
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if request.user.es_admin:
            return True
        if hasattr(obj, 'usuario'):
            return obj.usuario == request.user
        return False
