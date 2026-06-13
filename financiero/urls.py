from django.urls import path
from financiero import views

app_name = 'financiero'

urlpatterns = [
    path('',                              views.dashboard,        name='dashboard'),
    path('registros/',                    views.registro_list,    name='registro_list'),
    path('registros/nuevo/',              views.registro_create,  name='registro_create'),
    path('registros/<int:pk>/editar/',    views.registro_update,  name='registro_update'),
    path('registros/<int:pk>/eliminar/',  views.registro_delete,  name='registro_delete'),
    path('analisis/',                     views.analisis,         name='analisis'),
]
