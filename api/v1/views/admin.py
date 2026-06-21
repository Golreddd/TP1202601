"""
API del panel administrativo (solo rol ADMIN).

GET    /api/v1/admin/usuarios/               → Lista usuarios (filtros: search, activo, rol)
POST   /api/v1/admin/usuarios/               → Crear usuario directamente
GET    /api/v1/admin/usuarios/<id>/          → Detalle de usuario
PUT    /api/v1/admin/usuarios/<id>/estado/   → Activar / desactivar cuenta
PUT    /api/v1/admin/usuarios/<id>/rol/      → Cambiar rol (USUARIO ↔ ADMIN)
GET    /api/v1/admin/actividad/              → Audit log
GET    /api/v1/admin/metricas/               → Métricas del sistema

Seguridad:
  - Todos los endpoints requieren token JWT (IsAuthenticated)
  - Adicionalmente requieren rol ADMIN (EsAdminSigamos)
  - Los roles se asignan por defecto como USUARIO al registrarse
  - Solo el admin puede cambiar roles
"""
import logging

from rest_framework import status
from rest_framework.generics import RetrieveAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Rol, Usuario
from panel_admin.models import AuditLog
from recomendaciones.models import ResultadoML
from core.permissions import EsAdminSigamos
from api.v1.serializers.accounts import (
    UsuarioListSerializer,
    UsuarioRegistroSerializer,
    UsuarioSerializer,
)

logger = logging.getLogger(__name__)


class AdminUsuarioListView(APIView):
    """
    GET  /api/v1/admin/usuarios/  → Lista todos los usuarios con filtros opcionales
    POST /api/v1/admin/usuarios/  → Crea un usuario directamente (sin que se registre solo)

    Filtros GET:
      ?search=texto        → busca en nickname y email
      ?activo=true/false   → filtra por estado
      ?rol=USUARIO/ADMIN   → filtra por rol
    """
    permission_classes = [EsAdminSigamos]

    def get(self, request):
        from django.db.models import Count, Q

        qs = Usuario.objects.select_related('rol').annotate(
            total_registros=Count('registros', distinct=True)
        ).order_by('-date_joined')

        # Filtros opcionales
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(nickname__icontains=search) | Q(email__icontains=search)
            )

        activo = request.query_params.get('activo')
        if activo is not None:
            qs = qs.filter(is_active=activo.lower() == 'true')

        rol_filtro = request.query_params.get('rol', '').strip().upper()
        if rol_filtro in (Rol.USUARIO, Rol.ADMIN):
            qs = qs.filter(rol__nombre=rol_filtro)

        serializer = UsuarioListSerializer(qs, many=True)
        return Response({
            'total': qs.count(),
            'usuarios': serializer.data,
        })

    def post(self, request):
        """
        Crea un usuario directamente desde el panel de administración.
        El rol USUARIO se asigna automáticamente vía signal (igual que el registro normal).
        Solo el admin puede usar este endpoint.
        """
        serializer = UsuarioRegistroSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        AuditLog.registrar(
            admin=request.user,
            accion='CREAR_USUARIO',
            usuario_objetivo=user,
            detalle=f'Usuario {user.nickname} creado por administrador.',
            request=request,
        )

        return Response(
            UsuarioSerializer(user).data,
            status=status.HTTP_201_CREATED,
        )


class AdminUsuarioDetailView(RetrieveAPIView):
    """GET /api/v1/admin/usuarios/<id>/"""
    serializer_class   = UsuarioSerializer
    permission_classes = [EsAdminSigamos]
    queryset           = Usuario.objects.select_related('rol').all()

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        AuditLog.registrar(
            admin=request.user,
            accion='VER_USUARIO',
            usuario_objetivo=instance,
            request=request,
        )
        return Response(self.get_serializer(instance).data)


class AdminToggleEstadoView(APIView):
    """
    PUT /api/v1/admin/usuarios/<id>/estado/
    Activa o desactiva la cuenta del usuario.
    Body: {"activo": true}  o  {"activo": false}
    """
    permission_classes = [EsAdminSigamos]

    def put(self, request, pk):
        try:
            usuario = Usuario.objects.get(pk=pk)
        except Usuario.DoesNotExist:
            return Response(
                {'error': 'Usuario no encontrado.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if usuario == request.user:
            return Response(
                {'error': 'No puedes modificar tu propia cuenta.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        activo = request.data.get('activo')
        if activo is None:
            return Response(
                {'error': 'Se requiere el campo "activo" (true o false).'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        usuario.is_active = bool(activo)
        usuario.save(update_fields=['is_active'])

        accion = 'ACTIVAR_USUARIO' if usuario.is_active else 'DESACTIVAR_USUARIO'
        AuditLog.registrar(
            admin=request.user,
            accion=accion,
            usuario_objetivo=usuario,
            detalle=f'Estado cambiado a {"activo" if usuario.is_active else "inactivo"}.',
            request=request,
        )

        return Response({
            'mensaje': (
                f'Usuario {usuario.nickname} '
                f'{"activado" if usuario.is_active else "desactivado"}.'
            ),
            'usuario': UsuarioListSerializer(usuario).data,
        })


class AdminCambiarRolView(APIView):
    """
    PUT /api/v1/admin/usuarios/<id>/rol/
    Cambia el rol del usuario entre USUARIO y ADMIN.
    Body: {"rol": "ADMIN"}  o  {"rol": "USUARIO"}

    Solo el admin puede ejecutar este endpoint (EsAdminSigamos).
    Al registrarse, todo usuario recibe rol USUARIO por defecto (signal).
    """
    permission_classes = [EsAdminSigamos]

    def put(self, request, pk):
        try:
            usuario = Usuario.objects.select_related('rol').get(pk=pk)
        except Usuario.DoesNotExist:
            return Response(
                {'error': 'Usuario no encontrado.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if usuario == request.user:
            return Response(
                {'error': 'No puedes cambiar tu propio rol.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        nuevo_rol_nombre = request.data.get('rol', '').strip().upper()
        if nuevo_rol_nombre not in (Rol.USUARIO, Rol.ADMIN):
            return Response(
                {'error': f'Rol inválido. Valores permitidos: {Rol.USUARIO}, {Rol.ADMIN}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            nuevo_rol = Rol.objects.get(nombre=nuevo_rol_nombre)
        except Rol.DoesNotExist:
            return Response(
                {
                    'error': (
                        f'El rol "{nuevo_rol_nombre}" no existe en la BD. '
                        'Ejecuta los datos iniciales del schema SQL.'
                    )
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        rol_anterior = usuario.nombre_rol
        usuario.rol  = nuevo_rol
        usuario.save()  # save() sincroniza is_staff automáticamente

        AuditLog.registrar(
            admin=request.user,
            accion='CAMBIAR_ROL',
            usuario_objetivo=usuario,
            detalle=f'Rol cambiado de {rol_anterior} a {nuevo_rol.get_nombre_display()}.',
            request=request,
        )

        return Response({
            'mensaje': (
                f'Rol de {usuario.nickname} cambiado a '
                f'{nuevo_rol.get_nombre_display()}.'
            ),
            'usuario': UsuarioSerializer(usuario).data,
        })


class AdminActividadView(APIView):
    """
    GET /api/v1/admin/actividad/
    Retorna los últimos 100 registros del audit log.
    Soporta ?accion=ACTIVAR_USUARIO para filtrar por tipo de acción.
    """
    permission_classes = [EsAdminSigamos]

    def get(self, request):
        qs = AuditLog.objects.select_related(
            'admin', 'usuario_objetivo'
        ).order_by('-fecha')

        # Filtro opcional por tipo de acción
        accion_filtro = request.query_params.get('accion', '').strip()
        if accion_filtro:
            qs = qs.filter(accion=accion_filtro)

        qs = qs[:100]

        data = [
            {
                'id':                log.id,
                'fecha':             log.fecha.strftime('%d/%m/%Y %H:%M'),
                'admin':             log.admin.nickname if log.admin else 'Sistema',
                'accion':            log.accion,
                'accion_display':    log.get_accion_display(),
                'usuario_objetivo':  (
                    log.usuario_objetivo.nickname if log.usuario_objetivo else None
                ),
                'detalle':           log.detalle,
                'ip':                str(log.ip_address) if log.ip_address else None,
            }
            for log in qs
        ]

        AuditLog.registrar(
            admin=request.user,
            accion='VER_ESTADISTICAS',
            detalle='Vista de audit log.',
            request=request,
        )

        return Response({'total': len(data), 'logs': data})


class AdminMetricasView(APIView):
    """
    GET /api/v1/admin/metricas/
    Métricas globales del sistema para el dashboard administrativo.
    """
    permission_classes = [EsAdminSigamos]

    def get(self, request):
        from django.utils import timezone
        from datetime import timedelta
        from django.db.models import Count

        ahora        = timezone.now()
        hace_30_dias = ahora - timedelta(days=30)
        hace_7_dias  = ahora - timedelta(days=7)

        total_usuarios   = Usuario.objects.count()
        usuarios_activos = Usuario.objects.filter(is_active=True).count()
        nuevos_mes       = Usuario.objects.filter(date_joined__gte=hace_30_dias).count()
        nuevos_semana    = Usuario.objects.filter(date_joined__gte=hace_7_dias).count()

        # Distribución por rol
        por_rol = list(
            Usuario.objects.values('rol__nombre')
            .annotate(total=Count('id'))
            .order_by('rol__nombre')
        )

        from financiero.models import RegistroMensual
        total_registros = RegistroMensual.objects.count()
        registros_mes   = RegistroMensual.objects.filter(
            creado_en__gte=hace_30_dias
        ).count()

        total_analisis = ResultadoML.objects.count()
        analisis_mes   = ResultadoML.objects.filter(
            creado_en__gte=hace_30_dias
        ).count()

        clases = list(
            ResultadoML.objects.values('label_predicha')
            .annotate(total=Count('id'))
            .order_by('-total')
        )

        AuditLog.registrar(
            admin=request.user,
            accion='VER_ESTADISTICAS',
            detalle='Vista de métricas del sistema.',
            request=request,
        )

        return Response({
            'usuarios': {
                'total':         total_usuarios,
                'activos':       usuarios_activos,
                'inactivos':     total_usuarios - usuarios_activos,
                'nuevos_30_dias': nuevos_mes,
                'nuevos_7_dias':  nuevos_semana,
                'por_rol':       por_rol,
            },
            'registros': {
                'total':      total_registros,
                'ultimo_mes': registros_mes,
            },
            'analisis_ml': {
                'total':                 total_analisis,
                'ultimo_mes':            analisis_mes,
                'distribucion_clases':   clases,
            },
        })
