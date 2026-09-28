# -*- coding: utf-8 -*-
"""
Vocabulario del asistente de voz: jerga peruana, sinónimos y palabras clave por
categoría de gasto, tipo de ingreso, verbos, periodo y preguntas.

Solo datos (listas/diccionarios) — la lógica de interpretación vive en
financiero/voz.py. Mantener las claves de CATEGORIAS_GASTO alineadas con los
campos de financiero.models.RegistroMensual y con las claves GASTO_* que usa
el motor ML (src/pipeline/predict.py) y el plan de recomendaciones
(recomendaciones.models.PlanSeleccionado.gastos_sugeridos).
"""

# ── Categorías de gasto (8, igual que RegistroMensual) ─────────────────────────
# 'palabras' incluye el nombre formal de la categoría, sinónimos, jerga peruana,
# marcas/apps comunes y productos típicos de cada categoría.
CATEGORIAS_GASTO = {
    'gasto_alimentos': {
        'label': 'Alimentos', 'emoji': '🍔', 'clave_ml': 'GASTO_ALIMENTOS',
        'palabras': [
            'alimentos', 'alimentacion', 'comida', 'comer', 'almuerzo', 'almorzar',
            'desayuno', 'desayunar', 'cena', 'cenar', 'lonche', 'menu', 'mercado',
            'mercadeo', 'verdura', 'verduras', 'fruta', 'frutas', 'pollo',
            'polleria', 'chifa', 'restaurante', 'restaurant', 'delivery',
            'rappi', 'pedidosya', 'supermercado', 'plaza vea', 'plazavea',
            'metro', 'tottus', 'wong', 'vivanda', 'panaderia', 'pan', 'abarrotes',
            'bodega', 'gaseosa', 'snacks', 'snack', 'dulces', 'golosinas',
            'sanguche', 'sandwich', 'hamburguesa', 'pizza', 'brasa',
            'pollo a la brasa', 'cebiche', 'ceviche', 'jugo', 'cafe', 'lonchera',
            'canasta', 'víveres', 'viveres', 'carne', 'pescado', 'leche', 'huevos',
            'arroz', 'menestras', 'yapa',
            # Marcas / cadenas conocidas (Perú)
            'kfc', 'mcdonalds', 'mc donalds', 'burger king', 'bembos', 'chinawok',
            'china wok', 'pizza hut', 'dominos', 'papa johns', 'starbucks',
            'juan valdez', 'norkys', 'rockys', 'pardos', 'pardos chicken',
            'popeyes', 'subway', 'dunkin', 'cinnabon', 'tanta', 'la baguette',
            'san fernando', 'freshmart', 'makro', 'mass', 'don belisario',
            'la lucha', 'chifa royal',
        ],
    },
    'gasto_vestido': {
        'label': 'Ropa', 'emoji': '👗', 'clave_ml': 'GASTO_VESTIDO',
        'palabras': [
            'ropa', 'vestido', 'polo', 'polera', 'pantalon', 'jean', 'zapatilla',
            'zapatillas', 'zapato', 'zapatos', 'casaca', 'chompa', 'falda',
            'camisa', 'blusa', 'short', 'interiores', 'medias', 'gorra', 'correa',
            'cartera', 'mochila', 'saco', 'abrigo', 'moda', 'tienda de ropa',
            'saga', 'ripley', 'oechsle', 'zara', 'sandalias', 'chalina', 'traje',
            # Marcas / tiendas conocidas
            'topitop', 'index', 'forever 21', 'forever21', 'triathlon',
            'adidas', 'nike', 'puma', 'reebok', 'skechers', 'bata',
            'platanitos', 'payless', 'renzo costa',
        ],
    },
    'gasto_vivienda_servicios': {
        'label': 'Vivienda y servicios', 'emoji': '🏠', 'clave_ml': 'GASTO_VIVIENDA_SERVICIOS',
        'palabras': [
            'alquiler', 'renta', 'arriendo', 'luz', 'electricidad', 'agua', 'gas',
            'wifi de casa', 'internet de casa', 'cable', 'mantenimiento',
            'condominio', 'predial', 'arbitrios', 'servicios', 'recibo',
            'recibos', 'vivienda', 'departamento', 'casa', 'balon de gas',
            'balón de gas', 'sedapal', 'luz del sur', 'enel',
            # Marcas / empresas de servicios y mejoras del hogar
            'calidda', 'edelnor', 'movistar hogar', 'claro hogar', 'winner',
            'sodimac', 'promart', 'maestro',
        ],
    },
    'gasto_salud': {
        'label': 'Salud', 'emoji': '💊', 'clave_ml': 'GASTO_SALUD',
        'palabras': [
            'salud', 'doctor', 'medico', 'medicina', 'medicinas', 'farmacia',
            'botica', 'pastillas', 'consulta', 'clinica', 'hospital', 'dentista',
            'odontologo', 'psicologo', 'terapia', 'seguro medico', 'essalud',
            'lentes', 'optica', 'analisis', 'vacuna', 'inkafarma', 'mifarma',
            'boticas peru',
            # Marcas / clínicas y seguros de salud conocidos
            'rimac', 'pacifico salud', 'mapfre', 'la positiva',
            'clinica ricardo palma', 'clinica internacional', 'clinica delgado',
            'auna', 'farmacia universal', 'boticas y salud',
        ],
    },
    'gasto_transporte': {
        'label': 'Transporte', 'emoji': '🚌', 'clave_ml': 'GASTO_TRANSPORTE',
        'palabras': [
            'transporte', 'pasaje', 'pasajes', 'combi', 'micro', 'bus', 'buses',
            'taxi', 'uber', 'indrive', 'in drive', 'cabify', 'didi',
            'metropolitano', 'metro de lima', 'tren', 'gasolina', 'grifo',
            'peaje', 'estacionamiento', 'cochera', 'moto', 'mototaxi',
            'colectivo', 'flete', 'recarga de tarjeta', 'tarjeta lima', 'movilidad',
            # Apps y marcas conocidas de transporte/combustible
            'beat', 'primax', 'repsol', 'pecsa', 'petroperu', 'terpel',
        ],
    },
    'gasto_comunicaciones': {
        'label': 'Comunicaciones', 'emoji': '📱', 'clave_ml': 'GASTO_COMUNICACIONES',
        'palabras': [
            'comunicaciones', 'comunicacion', 'celular', 'recarga',
            'plan de celular', 'plan celular',
            'internet movil', 'datos moviles', 'claro', 'movistar', 'entel',
            'bitel', 'netflix', 'spotify', 'disney', 'disney plus', 'youtube premium',
            'streaming', 'suscripcion', 'suscripciones', 'chip',
            # Otras plataformas de streaming conocidas
            'hbo', 'hbo max', 'amazon prime', 'prime video', 'directv',
            'directv go', 'star plus', 'crunchyroll', 'paramount plus',
        ],
    },
    'gasto_educacion': {
        'label': 'Educación', 'emoji': '🎓', 'clave_ml': 'GASTO_EDUCACION',
        'palabras': [
            'educacion', 'estudios', 'universidad', 'instituto', 'colegio', 'pension',
            'mensualidad', 'matricula', 'libros', 'utiles', 'curso', 'cursos',
            'capacitacion', 'clases', 'profesor particular', 'academia',
            'carpeta', 'cuadernos', 'ingles', 'idiomas',
            # Universidades / institutos conocidos
            'utp', 'upc', 'ulima', 'pucp', 'usil', 'cibertec', 'senati', 'idat',
            'universidad continental', 'cesar vallejo', 'san marcos', 'unmsm',
            'esan', 'unfv', 'uni', 'unac',
        ],
    },
    'gasto_otros_bienes': {
        'label': 'Otros gastos', 'emoji': '🛒', 'clave_ml': 'GASTO_OTROS_BIENES',
        'palabras': [
            'chela', 'chelas', 'cerveza', 'trago', 'licor', 'fiesta', 'salida',
            'salir', 'cine', 'pelicula', 'juegos', 'videojuego', 'videojuegos',
            'regalo', 'regalos', 'cumpleanos', 'diversion', 'bar', 'discoteca',
            'antojo', 'gustito', 'gustitos', 'otros gastos', 'otras cosas',
            'accesorios', 'maquillaje', 'cigarros', 'cigarro', 'mascota',
            'mascotas', 'veterinario', 'lujos', 'hobbies', 'pasatiempo',
            'apuestas', 'polla', 'tragamonedas',
            # Marcas / cadenas de entretenimiento conocidas
            'cineplanet', 'cinemark', 'cinepolis', 'playstation', 'play station',
            'xbox', 'steam', 'nintendo',
        ],
    },
}

# ── Campos de ingreso (3, igual que RegistroMensual) ───────────────────────────
CAMPOS_INGRESO = {
    'ing_planilla': {
        'label': 'Ingreso en planilla', 'emoji': '💰',
        'palabras': [
            'sueldo', 'planilla', 'quincena', 'mi pago', 'salario', 'haber',
            'sueldo del trabajo', 'pago mensual', 'pago quincenal',
        ],
    },
    'bonif_monto': {
        'label': 'Bonificación', 'emoji': '🎁',
        'palabras': [
            'bono', 'bonificacion', 'gratificacion', 'cts', 'aguinaldo',
            'utilidades', 'reintegro', 'plata de mi mama', 'plata de mi papa',
            'plata de mi familia', 'plata de la familia', 'me dieron mis papas',
            'me dio mi mama', 'mi mama me dio', 'me dio mi papa', 'mi papa me dio',
            'mi mama me regalo', 'mi papa me regalo', 'mi familia me dio',
            'me ayudo mi mama', 'me ayudo mi papa', 'me regalaron', 'me regalo',
            'regalo de cumpleanos', 'propina de mis papas', 'me apoyaron con',
            'me ayudaron con', 'plata de mi abuela', 'plata de mi abuelo',
            'mi abuela me dio', 'mi abuelo me dio', 'mi tio me dio', 'mi tia me dio',
            'me dio mi tio', 'me dio mi tia', 'plata de mi tio', 'plata de mi tia',
            'propina', 'propinas',
        ],
    },
    'ing_informal': {
        'label': 'Ingreso informal', 'emoji': '💰',
        'palabras': [
            'cachuelo', 'cachuelos', 'delivery', 'freelance', 'trabajo extra',
            'chamba extra', 'changa', 'negocio', 'ventas', 'comision',
            'vendi', 'independiente',
        ],
    },
}

# ── Verbos / frases disparadoras ───────────────────────────────────────────────
VERBOS_GASTO = [
    'gaste', 'gasto', 'gasta', 'gastando', 'gastare', 'gastaria', 'he gastado',
    'habia gastado', 'me gaste', 'pague', 'pago', 'paga', 'pagando', 'he pagado',
    'me costo', 'costo', 'me salio', 'salio en', 'compre', 'compro', 'comprando',
    'solte', 'bote', 'use', 'invertí en', 'invierto en', 'desembolse',
    'se me fue', 'se me fueron', 'gastandome', 'me lo gaste',
]

VERBOS_INGRESO = [
    'me pagaron', 'me pago', 'cobre', 'cobro', 'recibi', 'recibio', 'gane',
    'gano', 'me depositaron', 'me deposito', 'me transfirieron',
    'me transfirio', 'me yapearon', 'me yapeo', 'me plinearon', 'me plineo',
    'vendi', 'me cayo', 'cayo', 'entro', 'ingreso', 'me dieron', 'me dio',
    'me regalaron', 'me regalo', 'ingrese', 'he ganado', 'he recibido',
    'me llego',
]

# ── Periodo ─────────────────────────────────────────────────────────────────
PALABRAS_MES_PASADO = [
    'mes pasado', 'el mes pasado', 'mes anterior', 'el mes anterior',
]

# ── Disparadores de pregunta ────────────────────────────────────────────────
PALABRAS_PREGUNTA = [
    'cuanto', 'cuanta', 'cuantos', 'cuantas', 'cual', 'cuales', 'que', 'como voy',
    'voy bien', 'me queda', 'me quedan', 'me sobra', 'me sobran', 'me alcanza',
    'en que gasto mas', 'en que gasto', 'voy cumpliendo', 'cumplo mi plan',
]

# ── Disparadores de simulación / hipotético ────────────────────────────────
PALABRAS_SIMULACION = [
    'si gasto', 'si gastara', 'si gastase', 'si pago', 'si compro',
    'puedo gastar', 'podria gastar', 'me alcanzaria', 'que pasa si',
    'y si gasto', 'me alcanzaria para', 'alcanzaria para',
]

# ── Moneda extranjera (no soportada) ───────────────────────────────────────
PALABRAS_MONEDA_EXTRANJERA = [
    'dolares', 'dolar', 'usd', 'us$', 'cocos', 'verdes',
]

# ── Números en palabras (español) ──────────────────────────────────────────
UNIDADES = {
    'cero': 0, 'un': 1, 'uno': 1, 'una': 1, 'dos': 2, 'tres': 3, 'cuatro': 4,
    'cinco': 5, 'seis': 6, 'siete': 7, 'ocho': 8, 'nueve': 9, 'diez': 10,
    'once': 11, 'doce': 12, 'trece': 13, 'catorce': 14, 'quince': 15,
    'dieciseis': 16, 'diecisiete': 17, 'dieciocho': 18, 'diecinueve': 19,
    'veinte': 20, 'veintiuno': 21, 'veintiun': 21, 'veintidos': 22,
    'veintitres': 23, 'veinticuatro': 24, 'veinticinco': 25, 'veintiseis': 26,
    'veintisiete': 27, 'veintiocho': 28, 'veintinueve': 29,
}
DECENAS = {
    'treinta': 30, 'cuarenta': 40, 'cincuenta': 50, 'sesenta': 60,
    'setenta': 70, 'ochenta': 80, 'noventa': 90,
}
CENTENAS = {
    'cien': 100, 'ciento': 100, 'doscientos': 200, 'trescientos': 300,
    'cuatrocientos': 400, 'quinientos': 500, 'seiscientos': 600,
    'setecientos': 700, 'ochocientos': 800, 'novecientos': 900,
}

# Unidades monetarias "neutras" que pueden aparecer pegadas al número: no
# valen nada por sí solas (solo confirman que "un/una N" se refiere a soles),
# a diferencia de DENOMINACIONES, cuyas palabras SÍ representan un monto fijo.
UNIDADES_MONEDA = ['soles', 'sol', 'mangos', 'mango', 's/', 's/.']

# Jerga peruana de billetes/montos: la palabra POR SÍ SOLA vale un monto fijo
# en soles ("un cheque" = 10, "dos ferros" = 200), igual que "mil" multiplica
# por 1000 — ver voz.py:_evaluar_entero. Con número adelante multiplica
# ("20 cheques" = 200); sin número, vale 1 vez ("cheque" = 10).
DENOMINACIONES = {
    'luca': 1, 'lucas': 1, 'luquita': 1, 'luquitas': 1,
    'cheque': 10, 'cheques': 10, 'cheke': 10, 'chekes': 10,
    'cheki': 10, 'chekis': 10,
    'ferro': 100, 'ferros': 100, 'ferrito': 100, 'ferritos': 100,
}

# Segmentadores para frases con varios montos ("30 en menú y 10 en pasajes").
# Se aplican como palabra suelta (\b) DESPUÉS de sustituir los números por
# marcadores NUM<k> (ver voz.py:_extraer_todos_los_numeros), así "treinta Y
# cinco" nunca se corta por la "y" conectora de un número compuesto.
SEPARADORES_ITEMS = ['y', 'ademas', 'tambien']
