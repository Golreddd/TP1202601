from django.urls import path
from panel_admin import views

app_name = 'panel_admin'

urlpatterns = [
    path('usuarios/',                       views.user_list,         name='user_list'),
    path('usuarios/<int:pk>/',              views.user_detail,       name='user_detail'),
    path('usuarios/<int:pk>/estado/',       views.user_toggle_active, name='user_toggle'),
    path('actividad/',                      views.activity_log,      name='activity'),
    path('metricas/',                       views.metrics_view,      name='metrics'),
]
