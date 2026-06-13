from django.urls import path
from recomendaciones import views

app_name = 'recomendaciones'

urlpatterns = [
    path('',                            views.ml_insights,        name='ml_insights'),
    path('historial/<int:pk>/',         views.historial_detalle,  name='historial_detalle'),
    path('metas/',                      views.metas,              name='metas'),
    path('metas/nueva/',                views.meta_create,   name='meta_create'),
    path('metas/<int:pk>/editar/',      views.meta_update,   name='meta_update'),
    path('metas/<int:pk>/eliminar/',    views.meta_delete,   name='meta_delete'),
]
