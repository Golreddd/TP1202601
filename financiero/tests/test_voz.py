# -*- coding: utf-8 -*-
"""
Tests del parser de voz (financiero.voz) y de los servicios que lo aplican
contra la base de datos (financiero.voz_servicios).
"""
from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase, TestCase

from accounts.models import Rol, Usuario
from financiero import voz_servicios as vs
from financiero.models import RegistroMensual
from financiero.voz import interpretar
from gamificacion.models import LogroUsuario
from recomendaciones.models import PlanSeleccionado, ResultadoML


class InterpretarVozTests(SimpleTestCase):
    """Pruebas puras del parser — no tocan la base de datos."""

    def test_gasto_simple_con_digitos(self):
        r = interpretar('gaste 50 en transporte')
        self.assertEqual(r['intencion'], 'registrar')
        self.assertEqual(r['items'], [{
            'tipo': 'gasto', 'campo': 'gasto_transporte',
            'etiqueta': 'Transporte', 'monto': 50.0,
        }])
        self.assertIsNone(r['faltante'])

    def test_jerga_peruana_de_transporte_y_moneda(self):
        r = interpretar('gasté 20 lucas en la combi')
        self.assertEqual(r['items'][0]['campo'], 'gasto_transporte')
        self.assertEqual(r['items'][0]['monto'], 20.0)

    def test_numero_en_palabras_simple(self):
        r = interpretar('gaste treinta y cinco en el menu')
        self.assertEqual(r['items'][0]['monto'], 35.0)
        self.assertEqual(r['items'][0]['campo'], 'gasto_alimentos')

    def test_numero_en_palabras_con_mil(self):
        r = interpretar('gaste mil doscientos en el alquiler')
        self.assertEqual(r['items'][0]['monto'], 1200.0)

    def test_numero_en_palabras_con_decimales(self):
        r = interpretar('gaste veinte con cincuenta en pasajes')
        self.assertEqual(r['items'][0]['monto'], 20.5)

    def test_varios_montos_en_una_frase(self):
        r = interpretar('gasté 30 en menú y 10 en pasajes')
        campos = {it['campo']: it['monto'] for it in r['items']}
        self.assertEqual(campos, {'gasto_alimentos': 30.0, 'gasto_transporte': 10.0})

    def test_falta_categoria(self):
        r = interpretar('gaste 50')
        self.assertEqual(r['items'], [])
        self.assertEqual(r['faltante'], {'tipo': 'categoria', 'monto': 50.0, 'item_tipo': 'gasto'})

    def test_falta_monto(self):
        r = interpretar('gaste en taxi')
        self.assertEqual(r['faltante'], {'tipo': 'monto', 'campo': 'gasto_transporte', 'item_tipo': 'gasto'})

    def test_completar_categoria_en_segundo_turno(self):
        r1 = interpretar('gaste 50')
        r2 = interpretar('transporte', contexto_previo=r1['texto_normalizado'])
        self.assertEqual(r2['items'], [{
            'tipo': 'gasto', 'campo': 'gasto_transporte',
            'etiqueta': 'Transporte', 'monto': 50.0,
        }])

    def test_completar_monto_en_segundo_turno(self):
        r1 = interpretar('gaste en taxi')
        r2 = interpretar('20', contexto_previo=r1['texto_normalizado'])
        self.assertEqual(r2['items'][0]['monto'], 20.0)

    def test_ingreso_planilla(self):
        r = interpretar('me pagaron 1500 de sueldo')
        self.assertEqual(r['items'][0], {
            'tipo': 'ingreso', 'campo': 'ing_planilla',
            'etiqueta': 'Ingreso en planilla', 'monto': 1500.0,
        })

    def test_ingreso_bonificacion_de_la_mama(self):
        r = interpretar('mi mama me dio 100')
        self.assertEqual(r['items'][0]['campo'], 'bonif_monto')

    def test_ingreso_por_defecto_informal(self):
        r = interpretar('gane 300')
        self.assertEqual(r['items'][0]['campo'], 'ing_informal')

    def test_ingreso_ambiguo_pide_tipo(self):
        # Sin separador ("y"/"además"), ambas palabras clave caen en el mismo
        # segmento y no se puede saber a qué tipo de ingreso pertenece el monto.
        r = interpretar('me pagaron 100 de sueldo con bonificacion')
        self.assertEqual(r['faltante'], {'tipo': 'tipo_ingreso', 'monto': 100.0, 'item_tipo': 'ingreso'})

    def test_ingreso_con_separador_se_interpreta_como_dos_ingresos(self):
        # "y" separa en dos ítems de ingreso distintos: el de planilla queda
        # completo (100) y el de bonificación queda pendiente de monto — no es
        # el mismo caso que la ambigüedad de arriba (documentado a propósito).
        r = interpretar('me pagaron 100 de sueldo y bono')
        self.assertEqual(r['items'], [{
            'tipo': 'ingreso', 'campo': 'ing_planilla',
            'etiqueta': 'Ingreso en planilla', 'monto': 100.0,
        }])
        self.assertEqual(r['faltante'], {'tipo': 'monto', 'campo': 'bonif_monto', 'item_tipo': 'ingreso'})

    def test_moneda_extranjera_rechazada(self):
        r = interpretar('gaste 20 dolares en comida')
        self.assertEqual(r['intencion'], 'moneda_no_soportada')

    def test_consulta_gasto_total(self):
        r = interpretar('cuanto he gastado este mes')
        self.assertEqual(r['intencion'], 'consultar')
        self.assertEqual(r['consulta'], {'tipo': 'gasto_total', 'campo': None, 'periodo': 'actual'})
        self.assertEqual(r['items'], [])

    def test_pregunta_con_verbo_de_gasto_no_se_confunde_con_registro(self):
        """'he gastado' es a la vez pregunta y verbo declarativo: sin monto ni
        categoría, debe quedar como pregunta pura, no como intento de registro."""
        r = interpretar('cuanto he gastado este mes')
        self.assertIsNone(r['faltante'])

    def test_pregunta_con_verbo_de_ingreso_no_se_confunde_con_registro(self):
        r = interpretar('cuanto gane este mes')
        self.assertEqual(r['intencion'], 'consultar')
        self.assertEqual(r['consulta']['tipo'], 'ingreso_total')

    def test_pregunta_de_categoria_sin_verbo_no_es_registro(self):
        r = interpretar('cuanto me queda de transporte')
        self.assertEqual(r['intencion'], 'consultar')
        self.assertEqual(r['consulta'], {'tipo': 'saldo_categoria', 'campo': 'gasto_transporte', 'periodo': 'actual'})

    def test_casuistica_gasto_y_pregunta_juntos(self):
        """'gasto 50 soles ¿cuánto me queda?' — mixta, falta la categoría."""
        r = interpretar('gasto 50 soles cuanto me queda')
        self.assertEqual(r['intencion'], 'mixta')
        self.assertEqual(r['faltante']['tipo'], 'categoria')
        self.assertEqual(r['consulta']['tipo'], 'saldo_categoria')

        r2 = interpretar('transporte', contexto_previo=r['texto_normalizado'])
        self.assertEqual(r2['intencion'], 'mixta')
        self.assertEqual(r2['items'][0]['campo'], 'gasto_transporte')
        self.assertEqual(r2['consulta']['campo'], 'gasto_transporte')

    def test_simulacion_no_se_confunde_con_registro(self):
        r = interpretar('si gasto 50 en ropa cuanto me quedaria')
        self.assertEqual(r['intencion'], 'simulacion')
        self.assertEqual(r['items'][0]['campo'], 'gasto_vestido')

    def test_frase_sin_sentido_es_desconocida(self):
        r = interpretar('hola como estas')
        self.assertEqual(r['intencion'], 'desconocida')
        self.assertTrue(r['ejemplos'])

    def test_una_no_es_monto_sin_unidad_monetaria(self):
        r = interpretar('una recarga de celular')
        self.assertEqual(r['intencion'], 'desconocida')

    def test_una_luca_es_un_sol(self):
        r = interpretar('gaste una luca en el mercado')
        self.assertEqual(r['items'][0]['monto'], 1.0)

    # ── Denominaciones de jerga (luca=1, cheque=10, ferro=100) ────────────────

    def test_denominacion_cheque_sola_vale_diez(self):
        r = interpretar('gaste un cheque en transporte')
        self.assertEqual(r['items'][0]['monto'], 10.0)

    def test_denominacion_ferro_sola_vale_cien(self):
        r = interpretar('gaste un ferro en transporte')
        self.assertEqual(r['items'][0]['monto'], 100.0)

    def test_denominacion_con_multiplicador(self):
        r = interpretar('gaste dos ferros en educacion')
        self.assertEqual(r['items'][0]['monto'], 200.0)

    def test_denominacion_con_digito_multiplicador(self):
        r = interpretar('gaste 20 cheques en el mercado')
        self.assertEqual(r['items'][0]['monto'], 200.0)

    def test_variantes_cheke_y_ferrito(self):
        self.assertEqual(interpretar('gaste un cheke en transporte')['items'][0]['monto'], 10.0)
        self.assertEqual(interpretar('gaste un ferrito en transporte')['items'][0]['monto'], 100.0)

    def test_frase_real_reportada_por_usuario_con_cheque_y_ferro(self):
        r = interpretar('hoy me gaste un cheque en comidas practicamente y un ferro en ropa')
        campos = {it['campo']: it['monto'] for it in r['items']}
        self.assertEqual(campos, {'gasto_alimentos': 10.0, 'gasto_vestido': 100.0})
        self.assertIsNone(r['faltante'])

    def test_frase_real_reportada_por_usuario_con_luquita(self):
        r = interpretar('oye gasta una luquita donando para alemania')
        self.assertEqual(r['faltante'], {'tipo': 'categoria', 'monto': 1.0, 'item_tipo': 'gasto'})

    # ── Plurales de categoría ("comidas" además de "comida") ──────────────────

    def test_categoria_en_plural(self):
        r = interpretar('gaste 30 en comidas')
        self.assertEqual(r['items'][0]['campo'], 'gasto_alimentos')

    def test_nombre_formal_de_categoria_educacion_y_comunicaciones(self):
        self.assertEqual(interpretar('gaste 30 en educacion')['items'][0]['campo'], 'gasto_educacion')
        self.assertEqual(interpretar('gaste 30 en comunicaciones')['items'][0]['campo'], 'gasto_comunicaciones')

    # ── Ingresos con verbos en singular / de un familiar cualquiera ───────────

    def test_ingreso_singular_me_dio_con_propina(self):
        r = interpretar('mi tio me dio 30 soles de propina')
        self.assertEqual(r['items'][0], {
            'tipo': 'ingreso', 'campo': 'bonif_monto',
            'etiqueta': 'Bonificación', 'monto': 30.0,
        })

    def test_ingreso_singular_sin_palabra_clave_cae_en_informal(self):
        r = interpretar('mi vecino me dio 50')
        self.assertEqual(r['items'][0]['tipo'], 'ingreso')
        self.assertEqual(r['items'][0]['campo'], 'ing_informal')

    def test_ingreso_verbo_singular_me_pago(self):
        r = interpretar('me pago 200 de sueldo')
        self.assertEqual(r['items'][0]['campo'], 'ing_planilla')


class VozServiciosTests(TestCase):
    """Pruebas de integración: aplicar/deshacer/responder contra la BD de test."""

    def setUp(self):
        rol, _ = Rol.objects.get_or_create(nombre=Rol.USUARIO, defaults={'descripcion': 'Usuario'})
        self.usuario = Usuario.objects.create(
            email='voz@example.com', username='voz_test', nickname='voz_test',
            rol=rol, edad=25, nivel_educ=3, miembros_hogar=1,
        )

    def _items(self, texto):
        return interpretar(texto)['items']

    def test_aplicar_crea_registro_del_mes_actual(self):
        resultado = vs.aplicar(self.usuario, self._items('gaste 50 en transporte'))
        registro = RegistroMensual.objects.get(usuario=self.usuario, periodo=vs.mes_actual())
        self.assertEqual(registro.gasto_transporte, Decimal('50.00'))
        self.assertIn('token_deshacer', resultado)

    def test_aplicar_suma_sobre_registro_existente(self):
        vs.aplicar(self.usuario, self._items('gaste 50 en transporte'))
        vs.aplicar(self.usuario, self._items('gaste 15 en taxi'))
        registro = RegistroMensual.objects.get(usuario=self.usuario, periodo=vs.mes_actual())
        self.assertEqual(registro.gasto_transporte, Decimal('65.00'))

    def test_aplicar_actualiza_racha_y_contador_de_voz(self):
        vs.aplicar(self.usuario, self._items('gaste 50 en transporte'))
        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.registros_voz, 1)
        self.assertEqual(self.usuario.racha.dias_consecutivos, 1)

    def test_aplicar_otorga_logro_manos_libres(self):
        vs.aplicar(self.usuario, self._items('gaste 50 en transporte'))
        self.assertTrue(
            LogroUsuario.objects.filter(usuario=self.usuario, logro__codigo='MANOS_LIBRES').exists()
        )

    def test_deshacer_revierte_el_monto(self):
        resultado = vs.aplicar(self.usuario, self._items('gaste 50 en transporte'))
        vs.aplicar(self.usuario, self._items('gaste 15 en taxi'))
        d = vs.deshacer(self.usuario, resultado['token_deshacer'])
        # El primer token ya no coincide con el estado actual del registro (65 - 50 = 15,
        # pero el token solo conoce su propio delta de 50): debe revertir igual porque
        # 65 >= 50, dejando 15.
        self.assertTrue(d['ok'])
        registro = RegistroMensual.objects.get(usuario=self.usuario, periodo=vs.mes_actual())
        self.assertEqual(registro.gasto_transporte, Decimal('15.00'))
        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.registros_voz, 1)

    def test_deshacer_borra_el_registro_si_queda_en_cero(self):
        resultado = vs.aplicar(self.usuario, self._items('gaste 50 en transporte'))
        d = vs.deshacer(self.usuario, resultado['token_deshacer'])
        self.assertTrue(d['ok'])
        self.assertFalse(RegistroMensual.objects.filter(usuario=self.usuario, periodo=vs.mes_actual()).exists())

    def test_deshacer_con_token_de_otro_usuario_falla(self):
        resultado = vs.aplicar(self.usuario, self._items('gaste 50 en transporte'))
        rol, _ = Rol.objects.get_or_create(nombre=Rol.USUARIO)
        otro = Usuario.objects.create(email='otro@example.com', username='otro', nickname='otro', rol=rol)
        d = vs.deshacer(otro, resultado['token_deshacer'])
        self.assertFalse(d['ok'])

    def test_deshacer_token_invalido_falla_controladamente(self):
        d = vs.deshacer(self.usuario, 'token-que-no-existe')
        self.assertFalse(d['ok'])

    def test_responder_gasto_total(self):
        vs.aplicar(self.usuario, self._items('gaste 50 en transporte'))
        r = vs.responder(self.usuario, {'tipo': 'gasto_total', 'campo': None, 'periodo': 'actual'})
        self.assertIn('50.00', r['texto'])

    def test_responder_sin_registro_avisa(self):
        r = vs.responder(self.usuario, {'tipo': 'gasto_total', 'campo': None, 'periodo': 'actual'})
        self.assertIn('No tienes ningún registro', r['texto'])

    def test_previsualizar_marca_exceso_de_plan(self):
        registro = RegistroMensual.objects.create(usuario=self.usuario, periodo=vs.mes_actual())
        resultado_ml = ResultadoML.objects.create(
            usuario=self.usuario, registro=registro, mes_referencia=registro,
            ahorro_actual=0, meta_validada=100, necesita_recortar=True,
            clase_predicha=0, label_predicha='Déficit', prob_ahorra=0.3, confianza=0.7,
        )
        PlanSeleccionado.objects.create(
            usuario=self.usuario, resultado=resultado_ml, nombre_plan='Equilibrado',
            ahorro_proyectado=100, meta_ahorro=100, activo=True,
            gastos_sugeridos={'GASTO_TRANSPORTE': 30.0},
        )
        preview = vs.previsualizar(self.usuario, self._items('gaste 50 en transporte'))
        self.assertTrue(preview['tiene_plan'])
        self.assertTrue(preview['excede_plan'])
