"""
Management command: recalcular_validacion_ml

Vuelve a clasificar, con el modelo ACTUAL (models/xgb_clf_model.pkl), el mismo registro
mensual que se usó en el primer análisis de cada usuario (ValidacionPrimerUso), y lo
contrasta con su clase real (ahorro = ingreso − gasto >= 0). Sirve para actualizar la
evaluación externa tras reentrenar el modelo.

Por defecto NO modifica la base de datos: imprime cada caso, la matriz de confusión y
las métricas con IC 95 % de Wilson, y guarda un CSV. Con --aplicar actualiza los casos.

Si el usuario editó su registro después del primer análisis, la predicción usaría datos
distintos de los que definieron clase_real. Esos casos se marcan como EDITADO (ingreso o
gasto actual distinto del guardado en la captura) y se excluyen de las métricas; con
--incluir-editados se cuentan igual. El perfil (nivel educativo, miembros del hogar) no se
guardó en la captura, por lo que sus cambios no pueden detectarse.

Uso:
    python manage.py recalcular_validacion_ml
    python manage.py recalcular_validacion_ml --csv salida.csv
    python manage.py recalcular_validacion_ml --aplicar
"""
import csv
import math

from django.core.management.base import BaseCommand

from financiero.models import RegistroMensual
from panel_admin.models import ValidacionPrimerUso
from src.predict import classify
from src.preprocessing import gasto_total, ing_total


def _wilson(k, n, z=1.959964):
    if n == 0:
        return (float('nan'), float('nan'))
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (round(c - h, 3), round(c + h, 3))


class Command(BaseCommand):
    help = 'Reclasifica los casos de validación con el modelo actual (no escribe salvo --aplicar).'

    def add_arguments(self, parser):
        parser.add_argument('--aplicar', action='store_true',
                            help='Actualiza clase_predicha, prob_ahorra y tipo en la BD.')
        parser.add_argument('--csv', default='validacion_ml_modelo_nuevo.csv')
        parser.add_argument('--incluir-editados', action='store_true',
                            help='Cuenta en las métricas los casos cuyo registro cambió.')

    def handle(self, *args, **opt):
        filas, tp, tn, fp, fn, editados = [], 0, 0, 0, 0, 0
        for v in ValidacionPrimerUso.objects.select_related('usuario', 'resultado').order_by('id'):
            reg = None
            if v.resultado_id:
                reg = v.resultado.mes_referencia or v.resultado.registro
            if reg is None:
                reg = RegistroMensual.objects.filter(usuario=v.usuario, periodo=v.periodo).first()
            if reg is None:
                self.stdout.write(self.style.WARNING(f'  {v.usuario.nickname}: sin registro, se omite'))
                continue
            d = reg.to_user_dict()
            editado = (abs(float(ing_total(d)) - float(v.ing_total)) > 0.5
                       or abs(float(gasto_total(d)) - float(v.gasto_total)) > 0.5)
            cls = classify(d)
            pred, real = int(cls['clase']), int(v.clase_real)
            tipo = ValidacionPrimerUso.clasificar_tipo(pred, real)
            cuenta = (not editado) or opt['incluir_editados']
            if cuenta:
                tp += tipo == 'TP'; tn += tipo == 'TN'; fp += tipo == 'FP'; fn += tipo == 'FN'
            else:
                editados += 1
            filas.append({'usuario': v.usuario.nickname, 'periodo': f'{v.periodo:%Y-%m}',
                          'clase_real': real, 'pred_anterior': v.clase_predicha,
                          'prob_anterior': round(v.prob_ahorra, 4), 'pred_nueva': pred,
                          'prob_nueva': round(cls['probabilidad_ahorra'], 4), 'tipo_nuevo': tipo,
                          'editado': int(editado), 'ing_guardado': round(float(v.ing_total), 2),
                          'ing_actual': round(float(ing_total(d)), 2),
                          'gasto_guardado': round(float(v.gasto_total), 2),
                          'gasto_actual': round(float(gasto_total(d)), 2)})
            marca = '  EDITADO' if editado else ''
            self.stdout.write(f"  {v.usuario.nickname:20} {v.periodo:%Y-%m} real={real} "
                              f"antes={v.clase_predicha} ahora={pred} p={cls['probabilidad_ahorra']:.3f} -> {tipo}{marca}")
            if opt['aplicar'] and cuenta:
                v.clase_predicha = pred
                v.prob_ahorra = float(cls['probabilidad_ahorra'])
                v.confianza = str(cls['confianza'])[:20]
                v.tipo = tipo
                v.save(update_fields=['clase_predicha', 'prob_ahorra', 'confianza', 'tipo'])

        n = tp + tn + fp + fn
        if filas:
            with open(opt['csv'], 'w', newline='', encoding='utf-8') as f:
                w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
                w.writeheader(); w.writerows(filas)
        acc = (tp + tn) / n if n else float('nan')
        prec = tp / (tp + fp) if tp + fp else float('nan')
        rec = tp / (tp + fn) if tp + fn else float('nan')
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else float('nan')
        den = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
        mcc = (tp * tn - fp * fn) / den if den else float('nan')
        self.stdout.write(self.style.SUCCESS(
            f'\nn={n} (excluidos por edición: {editados}) | TP={tp} TN={tn} FP={fp} FN={fn}\n'
            f'Accuracy={acc:.3f} IC95 {_wilson(tp + tn, n)}\n'
            f'Precision={prec:.3f} IC95 {_wilson(tp, tp + fp)}\n'
            f'Recall={rec:.3f} IC95 {_wilson(tp, tp + fn)}\n'
            f'F1={f1:.3f} | MCC={mcc:.3f} | Accuracy balanceada={(rec + (tn / (tn + fp) if tn + fp else float("nan"))) / 2:.3f}\n'
            f'CSV: {opt["csv"]} | {"BD ACTUALIZADA" if opt["aplicar"] else "sin cambios en BD (use --aplicar)"}'))
