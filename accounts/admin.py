from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from accounts.models import Rol, Usuario


@admin.register(Rol)
class RolAdmin(admin.ModelAdmin):
    list_display  = ('nombre', 'descripcion', 'total_usuarios')
    search_fields = ('nombre',)

    def total_usuarios(self, obj):
        return obj.usuarios.count()
    total_usuarios.short_description = 'Usuarios'


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display  = ('email', 'nickname', 'nombre_rol', 'is_active', 'perfil_completo', 'date_joined')
    list_filter   = ('rol', 'is_active')
    search_fields = ('email', 'nickname')
    ordering      = ('-date_joined',)

    fieldsets = UserAdmin.fieldsets + (
        ('Rol SIGAMOS', {'fields': ('nickname', 'rol')}),
        ('Perfil financiero (ML)', {'fields': ('edad', 'nivel_educ', 'miembros_hogar')}),
        ('Contacto', {'fields': ('telefono', 'ciudad')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('SIGAMOS', {'fields': ('nickname', 'email', 'rol')}),
    )
