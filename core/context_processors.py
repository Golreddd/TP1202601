"""Context processors globales de SIGAMOS (disponibles en todos los templates)."""


def plan_desactualizado(request):
    """Spec §8.2: aviso persistente (no bloqueante) si el usuario registró un mes nuevo
    sin actualizar/re-elegir su plan de ahorro desde ML Insights. Se calcula en cada
    request para que el banner en base.html sea consistente en toda la app."""
    if not request.user.is_authenticated:
        return {}

    from recomendaciones.models import PlanSeleccionado

    plan = (
        PlanSeleccionado.objects.filter(usuario=request.user, activo=True)
        .select_related('resultado__registro')
        .first()
    )
    if not plan or plan.aviso_descartado or not plan.resultado_id or not plan.resultado.registro_id:
        return {'plan_desactualizado': False}

    from financiero.models import RegistroMensual

    ultimo_registro = (
        RegistroMensual.objects.filter(usuario=request.user).order_by('-periodo').first()
    )
    desactualizado = bool(
        ultimo_registro and ultimo_registro.periodo > plan.resultado.registro.periodo
    )
    return {
        'plan_desactualizado': desactualizado,
        'plan_desactualizado_mes': plan.resultado.registro.periodo if desactualizado else None,
    }
