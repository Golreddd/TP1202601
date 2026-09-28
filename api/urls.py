"""
Punto de entrada de la API REST: delega todo en api.v1.urls (versión actual).
"""
from django.urls import include, path

urlpatterns = [
    path('v1/', include('api.v1.urls')),
]
