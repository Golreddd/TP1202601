from django.urls import path
from panel_admin import views

app_name = 'panel_admin'

urlpatterns = [
    path('usuarios/',                       views.user_list,         name='user_list'),
    path('usuarios/<int:pk>/',              views.user_detail,       name='user_detail'),
    path('usuarios/<int:pk>/estado/',       views.user_toggle_active, name='user_toggle'),
    path('actividad/',                      views.activity_log,      name='activity'),
    path('metricas/',                       views.metrics_view,      name='metrics'),
    path('validacion-ml/',                  views.validacion_ml,     name='validacion_ml'),
    path('validacion-ml/exportar/',         views.validacion_ml_export, name='validacion_ml_export'),
    path('evolucion-ahorro/',               views.evolucion_ahorro,  name='evolucion_ahorro'),
    path('evolucion-ahorro/exportar/',      views.evolucion_ahorro_export, name='evolucion_ahorro_export'),
]
