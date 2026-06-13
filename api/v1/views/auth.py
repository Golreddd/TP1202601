"""
API de autenticación y perfil de usuario.

POST   /api/v1/auth/registro/          → Crear cuenta
POST   /api/v1/auth/login/             → Login (obtener tokens JWT)
POST   /api/v1/auth/token/refresh/     → Renovar access token
POST   /api/v1/auth/logout/            → Invalidar refresh token
GET    /api/v1/auth/perfil/            → Ver perfil propio
PUT    /api/v1/auth/perfil/            → Actualizar perfil (incluye edad, nivel_educ, etc.)
PUT    /api/v1/auth/perfil/password/   → Cambiar contraseña
"""
from rest_framework import status
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView  # noqa: F401

from accounts.models import Usuario
from api.v1.serializers.accounts import (
    CambiarPasswordSerializer,
    UsuarioRegistroSerializer,
    UsuarioSerializer,
    UsuarioUpdateSerializer,
)
from gamificacion.services import verificar_y_otorgar_logros


class RegistroView(APIView):
    """
    POST /api/v1/auth/registro/
    Crea un nuevo usuario y retorna sus tokens JWT.
    El rol USUARIO se asigna automáticamente vía signal.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = UsuarioRegistroSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        refresh = RefreshToken.for_user(user)
        return Response(
            {
                'mensaje': f'Bienvenido a SIGAMOS, {user.nickname}!',
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'usuario': UsuarioSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(TokenObtainPairView):
    """
    POST /api/v1/auth/login/
    Autentica con email + password y retorna los tokens JWT
    junto con los datos del usuario.
    """
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)

        if response.status_code == status.HTTP_200_OK:
            from rest_framework_simplejwt.tokens import AccessToken
            try:
                token_obj = AccessToken(response.data['access'])
                user = Usuario.objects.select_related('rol').get(id=token_obj['user_id'])
                response.data['usuario'] = UsuarioSerializer(user).data
            except (Usuario.DoesNotExist, KeyError):
                pass

        return response


class LogoutView(APIView):
    """
    POST /api/v1/auth/logout/
    Invalida el refresh token (lo agrega al blacklist de simplejwt).
    Body: {"refresh": "<refresh_token>"}
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response(
                {'error': 'Se requiere el refresh token.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({'mensaje': 'Sesión cerrada correctamente.'})
        except TokenError:
            return Response(
                {'error': 'Token inválido o ya expirado.'},
                status=status.HTTP_400_BAD_REQUEST,
            )


class PerfilView(APIView):
    """
    GET  /api/v1/auth/perfil/  → datos del usuario autenticado
    PUT  /api/v1/auth/perfil/  → actualiza nickname, nombre, perfil financiero y contacto
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UsuarioSerializer(request.user).data)

    def put(self, request):
        serializer = UsuarioUpdateSerializer(
            request.user, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Verificar si se desbloqueó algún logro al completar el perfil
        verificar_y_otorgar_logros(user, contexto='perfil')

        return Response(UsuarioSerializer(user).data)


class CambiarPasswordView(APIView):
    """
    PUT /api/v1/auth/perfil/password/
    Cambia la contraseña verificando la contraseña actual.
    """
    permission_classes = [IsAuthenticated]

    def put(self, request):
        serializer = CambiarPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        if not user.check_password(serializer.validated_data['password_actual']):
            return Response(
                {'error': 'La contraseña actual es incorrecta.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(serializer.validated_data['password_nuevo'])
        user.save()
        return Response({'mensaje': 'Contraseña actualizada correctamente.'})
