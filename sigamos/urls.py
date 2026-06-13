"""
URLs raíz de SIGAMOS.

Estructura:
  /                    → redirige a /financiero/ (dashboard)
  /auth/               → vistas Django (login, register, logout, perfil)
  /financiero/         → vistas Django (dashboard, registros, análisis)
  /recomendaciones/    → vistas Django (ML insights, metas)
  /gamificacion/       → vistas Django (logros, progreso)
  /panel-admin/        → vistas Django (admin panel)
  /api/v1/             → DRF API (JWT, endpoints JSON — testeable con Postman)
  /django-admin/       → admin interno de Django
"""
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    # ── Admin interno Django ───────────────────────────────────────────────
    path('django-admin/', admin.site.urls),

    # ── API REST (DRF + JWT) ───────────────────────────────────────────────
    path('api/', include('api.urls')),

    # ── Vistas Django (páginas completas con templates) ───────────────────
    path('auth/', include('accounts.urls', namespace='accounts')),
    path('financiero/', include('financiero.urls', namespace='financiero')),
    path('recomendaciones/', include('recomendaciones.urls', namespace='recomendaciones')),
    path('gamificacion/', include('gamificacion.urls', namespace='gamificacion')),
    path('panel-admin/', include('panel_admin.urls', namespace='panel_admin')),

    # ── Raíz → dashboard ──────────────────────────────────────────────────
    path('', RedirectView.as_view(url='/financiero/', permanent=False)),
]
