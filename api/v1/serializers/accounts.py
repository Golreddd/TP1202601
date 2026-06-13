from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from accounts.models import Rol, Usuario


# ── Rol ───────────────────────────────────────────────────────────────────────

class RolSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Rol
        fields = ['id', 'nombre', 'descripcion']


# ── Usuario (lectura completa) ────────────────────────────────────────────────

class UsuarioSerializer(serializers.ModelSerializer):
    """Lectura completa del usuario autenticado."""
    rol        = RolSerializer(read_only=True)
    nombre_rol = serializers.CharField(read_only=True)
    es_admin   = serializers.BooleanField(read_only=True)
    perfil_completo = serializers.BooleanField(read_only=True)
    nivel_educ_display = serializers.CharField(
        source='get_nivel_educ_display', read_only=True
    )

    class Meta:
        model  = Usuario
        fields = [
            'id', 'email', 'nickname', 'first_name', 'last_name',
            'rol', 'nombre_rol', 'es_admin',
            'is_active', 'date_joined',
            # Perfil financiero (ML)
            'edad', 'nivel_educ', 'nivel_educ_display', 'miembros_hogar',
            # Contacto
            'telefono', 'ciudad',
            # Computed
            'perfil_completo',
        ]
        read_only_fields = fields


# ── Registro de nuevo usuario ─────────────────────────────────────────────────

class UsuarioRegistroSerializer(serializers.ModelSerializer):
    """POST /api/v1/auth/registro/ — El rol USUARIO se asigna automáticamente."""
    password  = serializers.CharField(write_only=True, min_length=8)
    password2 = serializers.CharField(write_only=True, label='Confirmar contraseña')

    class Meta:
        model  = Usuario
        fields = ['email', 'nickname', 'first_name', 'last_name', 'password', 'password2']

    def validate_email(self, value):
        if Usuario.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('Este correo ya está registrado.')
        return value.lower()

    def validate_nickname(self, value):
        if Usuario.objects.filter(nickname__iexact=value).exists():
            raise serializers.ValidationError('Este nickname ya está en uso.')
        if len(value) < 3:
            raise serializers.ValidationError('El nickname debe tener al menos 3 caracteres.')
        return value

    def validate_password(self, value):
        validate_password(value)
        return value

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({'password2': 'Las contraseñas no coinciden.'})
        return attrs

    def create(self, validated_data):
        validated_data.pop('password2')
        password = validated_data.pop('password')
        user = Usuario(**validated_data)
        user.username = validated_data.get('nickname')
        user.set_password(password)
        user.save()
        return user


# ── Actualización de perfil ───────────────────────────────────────────────────

class UsuarioUpdateSerializer(serializers.ModelSerializer):
    """PUT /api/v1/auth/perfil/"""

    class Meta:
        model  = Usuario
        fields = [
            'nickname', 'first_name', 'last_name',
            'edad', 'nivel_educ', 'miembros_hogar',
            'telefono', 'ciudad',
        ]

    def validate_nickname(self, value):
        user = self.instance
        if Usuario.objects.filter(nickname__iexact=value).exclude(pk=user.pk).exists():
            raise serializers.ValidationError('Este nickname ya está en uso.')
        return value

    def validate_nivel_educ(self, value):
        if value is not None and value not in range(1, 7):
            raise serializers.ValidationError('Nivel educativo debe estar entre 1 y 6.')
        return value

    def validate_edad(self, value):
        if value is not None and (value < 15 or value > 80):
            raise serializers.ValidationError('Edad debe estar entre 15 y 80 años.')
        return value

    def validate_miembros_hogar(self, value):
        if value is not None and (value < 1 or value > 20):
            raise serializers.ValidationError('Miembros del hogar debe estar entre 1 y 20.')
        return value


# ── Cambio de contraseña ──────────────────────────────────────────────────────

class CambiarPasswordSerializer(serializers.Serializer):
    """PUT /api/v1/auth/perfil/password/"""
    password_actual  = serializers.CharField(write_only=True)
    password_nuevo   = serializers.CharField(write_only=True, min_length=8)
    password_nuevo2  = serializers.CharField(write_only=True)

    def validate_password_nuevo(self, value):
        validate_password(value)
        return value

    def validate(self, attrs):
        if attrs['password_nuevo'] != attrs['password_nuevo2']:
            raise serializers.ValidationError(
                {'password_nuevo2': 'Las contraseñas nuevas no coinciden.'}
            )
        return attrs


# ── Lista de usuarios para panel admin ────────────────────────────────────────

class UsuarioListSerializer(serializers.ModelSerializer):
    """Serializer reducido para GET /api/v1/admin/usuarios/"""
    rol             = RolSerializer(read_only=True)
    nombre_rol      = serializers.CharField(read_only=True)
    total_registros = serializers.IntegerField(default=0)  # viene de annotate()

    class Meta:
        model  = Usuario
        fields = [
            'id', 'email', 'nickname', 'first_name', 'last_name',
            'rol', 'nombre_rol',
            'is_active', 'date_joined', 'last_login',
            'perfil_completo', 'total_registros',
        ]
        read_only_fields = fields
