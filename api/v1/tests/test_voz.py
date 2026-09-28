# -*- coding: utf-8 -*-
"""
Tests de la API del asistente de voz (/api/v1/voz/...).
"""
from django.test import TestCase
from django.urls import reverse

from accounts.models import Rol, Usuario
from financiero.models import RegistroMensual
from financiero import voz_servicios as vs


class ApiVozTests(TestCase):
    def setUp(self):
        rol, _ = Rol.objects.get_or_create(nombre=Rol.USUARIO, defaults={'descripcion': 'Usuario'})
        self.usuario = Usuario.objects.create(
            email='apivoz@example.com', username='apivoz', nickname='apivoz',
            rol=rol, edad=25, nivel_educ=3, miembros_hogar=1,
        )
        self.client.force_login(self.usuario)

    def test_requiere_autenticacion(self):
        self.client.logout()
        r = self.client.post(reverse('api_voz_interpretar'), {'texto': 'gaste 10 en taxi'},
                              content_type='application/json')
        self.assertEqual(r.status_code, 401)

    def test_interpretar_devuelve_faltante_categoria(self):
        r = self.client.post(reverse('api_voz_interpretar'), {'texto': 'gaste 50'},
                              content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['faltante']['tipo'], 'categoria')

    def test_flujo_completo_interpretar_confirmar_deshacer(self):
        r1 = self.client.post(reverse('api_voz_interpretar'), {'texto': 'gaste 50'},
                               content_type='application/json')
        contexto = r1.json()['texto_normalizado']

        r2 = self.client.post(reverse('api_voz_interpretar'),
                               {'texto': 'transporte', 'contexto_previo': contexto},
                               content_type='application/json')
        self.assertEqual(r2.status_code, 200)
        body2 = r2.json()
        self.assertEqual(body2['items'][0]['campo'], 'gasto_transporte')
        self.assertIn('previsualizacion', body2)

        r3 = self.client.post(reverse('api_voz_confirmar'), {'items': body2['items']},
                               content_type='application/json')
        self.assertEqual(r3.status_code, 201)
        body3 = r3.json()

        registro = RegistroMensual.objects.get(usuario=self.usuario, periodo=vs.mes_actual())
        self.assertEqual(registro.gasto_transporte, 50)

        r4 = self.client.post(reverse('api_voz_deshacer'), {'token': body3['token_deshacer']},
                               content_type='application/json')
        self.assertEqual(r4.status_code, 200)
        self.assertFalse(RegistroMensual.objects.filter(usuario=self.usuario, periodo=vs.mes_actual()).exists())

    def test_confirmar_rechaza_campo_invalido(self):
        r = self.client.post(
            reverse('api_voz_confirmar'),
            {'items': [{'tipo': 'gasto', 'campo': 'campo_invalido', 'etiqueta': 'x', 'monto': 10}]},
            content_type='application/json',
        )
        self.assertEqual(r.status_code, 400)

    def test_confirmar_rechaza_monto_negativo(self):
        r = self.client.post(
            reverse('api_voz_confirmar'),
            {'items': [{'tipo': 'gasto', 'campo': 'gasto_transporte', 'etiqueta': 'Transporte', 'monto': -5}]},
            content_type='application/json',
        )
        self.assertEqual(r.status_code, 400)

    def test_moneda_no_soportada_no_crea_previsualizacion(self):
        r = self.client.post(reverse('api_voz_interpretar'), {'texto': 'gaste 20 dolares en comida'},
                              content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['intencion'], 'moneda_no_soportada')
        self.assertNotIn('previsualizacion', r.json())

    def test_pregunta_pura_devuelve_respuesta(self):
        self.client.post(reverse('api_voz_confirmar'), {
            'items': [{'tipo': 'gasto', 'campo': 'gasto_transporte', 'etiqueta': 'Transporte', 'monto': 50}],
        }, content_type='application/json')
        r = self.client.post(reverse('api_voz_interpretar'), {'texto': 'cuanto he gastado este mes'},
                              content_type='application/json')
        body = r.json()
        self.assertEqual(body['intencion'], 'consultar')
        self.assertIn('50.00', body['respuesta']['texto'])
