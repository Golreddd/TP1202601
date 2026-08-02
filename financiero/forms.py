from datetime import date

from django import forms
from financiero.models import RegistroMensual


INPUT = {'class': 'form-input'}


class RegistroMensualForm(forms.ModelForm):
    """
    Formulario para crear/editar un RegistroMensual.
    El campo `periodo` usa un input type=month (YYYY-MM) y se convierte
    automáticamente a la fecha del primer día del mes (YYYY-MM-01).
    """
    periodo = forms.CharField(
        label='Período (mes)',
        widget=forms.DateInput(attrs={**INPUT, 'type': 'month'}),
    )

    class Meta:
        model = RegistroMensual
        fields = [
            'periodo',
            'ing_planilla', 'ing_informal', 'bonif_monto',
            'gasto_alimentos', 'gasto_vestido', 'gasto_vivienda_servicios',
            'gasto_salud', 'gasto_transporte', 'gasto_comunicaciones',
            'gasto_educacion', 'gasto_otros_bienes',
        ]
        widgets = {
            'ing_planilla':            forms.NumberInput(attrs={**INPUT, 'min': 0, 'step': '0.01'}),
            'ing_informal':            forms.NumberInput(attrs={**INPUT, 'min': 0, 'step': '0.01'}),
            'bonif_monto':             forms.NumberInput(attrs={**INPUT, 'min': 0, 'step': '0.01'}),
            'gasto_alimentos':         forms.NumberInput(attrs={**INPUT, 'min': 0, 'step': '0.01'}),
            'gasto_vestido':           forms.NumberInput(attrs={**INPUT, 'min': 0, 'step': '0.01'}),
            'gasto_vivienda_servicios':forms.NumberInput(attrs={**INPUT, 'min': 0, 'step': '0.01'}),
            'gasto_salud':             forms.NumberInput(attrs={**INPUT, 'min': 0, 'step': '0.01'}),
            'gasto_transporte':        forms.NumberInput(attrs={**INPUT, 'min': 0, 'step': '0.01'}),
            'gasto_comunicaciones':    forms.NumberInput(attrs={**INPUT, 'min': 0, 'step': '0.01'}),
            'gasto_educacion':         forms.NumberInput(attrs={**INPUT, 'min': 0, 'step': '0.01'}),
            'gasto_otros_bienes':      forms.NumberInput(attrs={**INPUT, 'min': 0, 'step': '0.01'}),
        }

    def clean_periodo(self):
        value = self.cleaned_data.get('periodo', '')
        if not value:
            raise forms.ValidationError('Este campo es requerido.')
        try:
            parts = value.split('-')
            return date(int(parts[0]), int(parts[1]), 1)
        except (ValueError, IndexError, TypeError):
            raise forms.ValidationError('Formato inválido. Selecciona un mes válido.')

    def clean(self):
        """El ingreso total del mes debe ser > 0.

        Sin ingreso no existe la identidad `ahorro = ingreso − gasto` sobre la que
        opera el análisis (la tasa de ahorro sería una división entre cero). La API
        ya exigía esto en RegistroMensualSerializer.validate(); aquí se replica para
        que el formulario web no pueda crear registros que luego el análisis no
        pueda procesar.
        """
        cleaned = super().clean()
        ing = (cleaned.get('ing_planilla') or 0) + (cleaned.get('ing_informal') or 0)
        if not self.errors and ing <= 0:
            raise forms.ValidationError(
                'El ingreso total del mes (planilla + informal) debe ser mayor a S/ 0.'
            )
        return cleaned

    def get_initial_periodo(self):
        """Retorna el período en formato YYYY-MM para el widget."""
        p = self.instance.periodo if self.instance and self.instance.pk else None
        return p.strftime('%Y-%m') if p else date.today().strftime('%Y-%m')
