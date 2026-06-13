"""
URLs de la API v1 de SIGAMOS.
Base: /api/v1/

╔══════════════════════════════════════════════════════════════╗
║  AUTENTICACIÓN                                               ║
╠══════════════════════════════════════════════════════════════╣
║  POST   auth/registro/                 SIN token (público)   ║
║  POST   auth/login/                    SIN token (público)   ║
║  POST   auth/token/refresh/            SIN token (público)   ║
║  POST   auth/logout/                   CON token             ║
║  GET    auth/perfil/                   CON token             ║
║  PUT    auth/perfil/                   CON token             ║
║  PUT    auth/perfil/password/          CON token             ║
╠══════════════════════════════════════════════════════════════╣
║  FINANCIERO (CRUD completo)                                  ║
╠══════════════════════════════════════════════════════════════╣
║  GET    financiero/dashboard/          CON token             ║
║  GET    financiero/analisis/           CON token             ║
║  GET    financiero/registros/          CON token             ║
║  POST   financiero/registros/          CON token             ║
║  GET    financiero/registros/ultimo/   CON token             ║
║  GET    financiero/registros/<id>/     CON token             ║
║  PUT    financiero/registros/<id>/     CON token             ║
║  PATCH  financiero/registros/<id>/     CON token             ║
║  DELETE financiero/registros/<id>/     CON token             ║
╠══════════════════════════════════════════════════════════════╣
║  RECOMENDACIONES                                             ║
╠══════════════════════════════════════════════════════════════╣
║  POST   recomendaciones/ejecutar/      CON token (datos reales, guarda)  ║
║  POST   recomendaciones/pronostico/    CON token (datos hipotéticos, NO guarda) ║
║  GET    recomendaciones/historial/     CON token             ║
║  GET    recomendaciones/historial/<id>/CON token             ║
║  DELETE recomendaciones/historial/<id>/CON token             ║
║  CRUD   recomendaciones/metas-mensuales/  CON token          ║
║  CRUD   recomendaciones/metas/            CON token          ║
╠══════════════════════════════════════════════════════════════╣
║  GAMIFICACIÓN                                                ║
╠══════════════════════════════════════════════════════════════╣
║  GET    gamificacion/racha/            CON token             ║
║  GET    gamificacion/logros/           CON token             ║
╠══════════════════════════════════════════════════════════════╣
║  ADMIN (requiere rol ADMIN)                                  ║
╠══════════════════════════════════════════════════════════════╣
║  GET    admin/usuarios/                CON token + ADMIN     ║
║  POST   admin/usuarios/                CON token + ADMIN     ║
║  GET    admin/usuarios/<id>/           CON token + ADMIN     ║
║  PUT    admin/usuarios/<id>/estado/    CON token + ADMIN     ║
║  PUT    admin/usuarios/<id>/rol/       CON token + ADMIN     ║
║  GET    admin/actividad/               CON token + ADMIN     ║
║  GET    admin/metricas/                CON token + ADMIN     ║
╚══════════════════════════════════════════════════════════════╝
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from api.v1.views.auth import (
    CambiarPasswordView,
    LoginView,
    LogoutView,
    PerfilView,
    RegistroView,
)
from api.v1.views.financiero import (
    AnalisisView,
    DashboardView,
    RegistroMensualViewSet,
)
from api.v1.views.gamificacion import LogrosView, RachaView
from api.v1.views.recomendaciones import (
    EjecutarMLView,
    ElegirPlanView,
    MetaLargoPlazoViewSet,
    MetaMensualViewSet,
    PronosticoMLView,
    ResultadoMLDetailView,
    ResultadoMLListView,
)
from api.v1.views.admin import (
    AdminActividadView,
    AdminCambiarRolView,
    AdminMetricasView,
    AdminToggleEstadoView,
    AdminUsuarioDetailView,
    AdminUsuarioListView,
)

# ── Router DRF — genera CRUD automáticamente para los ViewSets ────────────────
router = DefaultRouter()
router.register(
    r'financiero/registros',
    RegistroMensualViewSet,
    basename='registros',
)
router.register(
    r'recomendaciones/metas-mensuales',
    MetaMensualViewSet,
    basename='metas-mensuales',
)
router.register(
    r'recomendaciones/metas',
    MetaLargoPlazoViewSet,
    basename='metas',
)

urlpatterns = [

    # ── AUTENTICACIÓN ─────────────────────────────────────────────────────────
    # Solo /registro/ y /login/ son públicos (AllowAny).
    # Todos los demás requieren token JWT.
    path('auth/registro/',
         RegistroView.as_view(),
         name='api_registro'),

    path('auth/login/',
         LoginView.as_view(),
         name='api_login'),

    path('auth/token/refresh/',
         TokenRefreshView.as_view(),
         name='api_token_refresh'),

    path('auth/logout/',
         LogoutView.as_view(),
         name='api_logout'),

    path('auth/perfil/',
         PerfilView.as_view(),
         name='api_perfil'),

    path('auth/perfil/password/',
         CambiarPasswordView.as_view(),
         name='api_cambiar_password'),

    # ── FINANCIERO ────────────────────────────────────────────────────────────
    # Los endpoints de CRUD de registros vienen del router (ViewSet).
    path('financiero/dashboard/',
         DashboardView.as_view(),
         name='api_dashboard'),

    path('financiero/analisis/',
         AnalisisView.as_view(),
         name='api_analisis'),

    # ── RECOMENDACIONES ───────────────────────────────────────────────────────
    path('recomendaciones/ejecutar/',
         EjecutarMLView.as_view(),
         name='api_ejecutar_ml'),

    path('recomendaciones/pronostico/',
         PronosticoMLView.as_view(),
         name='api_pronostico_ml'),

    path('recomendaciones/historial/',
         ResultadoMLListView.as_view(),
         name='api_historial_ml'),

    path('recomendaciones/historial/<int:pk>/',
         ResultadoMLDetailView.as_view(),
         name='api_resultado_ml'),

    path('recomendaciones/elegir-plan/',
         ElegirPlanView.as_view(),
         name='api_elegir_plan'),
    # Las rutas de metas-mensuales y metas (largo plazo) vienen del router.

    # ── GAMIFICACIÓN ──────────────────────────────────────────────────────────
    path('gamificacion/racha/',
         RachaView.as_view(),
         name='api_racha'),

    path('gamificacion/logros/',
         LogrosView.as_view(),
         name='api_logros'),

    # ── PANEL ADMIN (requiere rol ADMIN) ──────────────────────────────────────
    path('admin/usuarios/',
         AdminUsuarioListView.as_view(),
         name='api_admin_usuarios'),

    path('admin/usuarios/<int:pk>/',
         AdminUsuarioDetailView.as_view(),
         name='api_admin_usuario_detail'),

    path('admin/usuarios/<int:pk>/estado/',
         AdminToggleEstadoView.as_view(),
         name='api_admin_toggle_estado'),

    path('admin/usuarios/<int:pk>/rol/',
         AdminCambiarRolView.as_view(),
         name='api_admin_cambiar_rol'),

    path('admin/actividad/',
         AdminActividadView.as_view(),
         name='api_admin_actividad'),

    path('admin/metricas/',
         AdminMetricasView.as_view(),
         name='api_admin_metricas'),

    # ── ViewSets (router) — debe ir al final ──────────────────────────────────
    path('', include(router.urls)),
]
