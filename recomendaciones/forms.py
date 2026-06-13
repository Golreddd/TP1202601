from django import forms
from recomendaciones.models import MetaLargoPlazo


INPUT = {'class': 'form-input'}


class MetaLargoPlazoForm(forms.ModelForm):
    class Meta:
        model = MetaLargoPlazo
        fields = ['nombre', 'icono', 'monto_objetivo', 'monto_actual', 'fecha_limite']
        widgets = {
            'nombre':         forms.TextInput(attrs={**INPUT, 'placeholder': 'Ej: Viaje a Machu Picchu'}),
            'icono':          forms.Select(attrs=INPUT),
            'monto_objetivo': forms.NumberInput(attrs={**INPUT, 'min': 1, 'step': '0.01', 'placeholder': '0.00'}),
            'monto_actual':   forms.NumberInput(attrs={**INPUT, 'min': 0, 'step': '0.01', 'placeholder': '0.00'}),
            'fecha_limite':   forms.DateInput(attrs={**INPUT, 'type': 'date'}),
        }

    def clean(self):
        cleaned = super().clean()
        objetivo = cleaned.get('monto_objetivo')
        actual   = cleaned.get('monto_actual', 0)
        if objetivo and actual and actual > objetivo:
            self.add_error('monto_actual', 'El monto ahorrado no puede superar el objetivo.')
        return cleaned
