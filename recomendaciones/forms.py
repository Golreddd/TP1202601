from datetime import date

from django import forms
from recomendaciones.models import MetaLargoPlazo


INPUT = {'class': 'form-input'}


class MetaLargoPlazoForm(forms.ModelForm):
    """
    Todo el seguimiento de la meta (meses_restantes, cuota_mensual_sugerida,
    plazo_estimado_meses, desviacion_plazo) razona en MESES, nunca en días — el día
    dentro del mes no se usa en ningún cálculo. Por eso `fecha_limite` usa el mismo
    patrón que RegistroMensualForm.periodo en financiero/forms.py: input type="month"
    + clean que normaliza a date(year, month, 1). El modelo sigue siendo un DateField
    normal; solo cambia cómo se captura en el formulario.
    """
    fecha_limite = forms.CharField(
        label='Fecha límite (mes)', required=False,
        widget=forms.DateInput(attrs={**INPUT, 'type': 'month'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # No se puede fijar una meta con fecha límite ya vencida (ver clean_fecha_limite,
        # que es la validación real): esto solo bloquea la selección en el picker nativo.
        self.fields['fecha_limite'].widget.attrs['min'] = date.today().strftime('%Y-%m')

    class Meta:
        model = MetaLargoPlazo
        fields = ['nombre', 'icono', 'monto_objetivo', 'monto_actual', 'fecha_limite']
        widgets = {
            'nombre':         forms.TextInput(attrs={**INPUT, 'placeholder': 'Ej: Viaje a Machu Picchu'}),
            'icono':          forms.Select(attrs=INPUT),
            'monto_objetivo': forms.NumberInput(attrs={**INPUT, 'min': 1, 'step': '0.01', 'placeholder': '0.00'}),
            'monto_actual':   forms.NumberInput(attrs={**INPUT, 'min': 0, 'step': '0.01', 'placeholder': '0.00'}),
        }

    def clean_fecha_limite(self):
        value = self.cleaned_data.get('fecha_limite', '')
        if not value:
            return None
        try:
            year, month = value.split('-')
            fecha = date(int(year), int(month), 1)
        except (ValueError, IndexError, TypeError):
            raise forms.ValidationError('Formato inválido. Selecciona un mes válido.')

        hoy = date.today()
        mes_actual = date(hoy.year, hoy.month, 1)
        # Si la meta YA tenía esta misma fecha guardada (no se tocó al editar otros
        # campos), se deja pasar aunque haya quedado en el pasado desde entonces — solo
        # se bloquea CREAR una meta con fecha vencida, o MOVER una existente al pasado.
        ya_estaba_guardada = self.instance.pk and self.instance.fecha_limite == fecha
        if fecha < mes_actual and not ya_estaba_guardada:
            raise forms.ValidationError('La fecha límite no puede ser un mes que ya pasó.')
        return fecha

    def clean(self):
        cleaned = super().clean()
        objetivo = cleaned.get('monto_objetivo')
        actual   = cleaned.get('monto_actual', 0)
        if objetivo and actual and actual > objetivo:
            self.add_error('monto_actual', 'El monto ahorrado no puede superar el objetivo.')
        return cleaned
