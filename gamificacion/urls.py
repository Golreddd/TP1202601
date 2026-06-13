from django.urls import path
from gamificacion import views

app_name = 'gamificacion'

urlpatterns = [
    path('logros/',   views.logros,   name='logros'),
    path('progreso/', views.progreso, name='progreso'),
]
