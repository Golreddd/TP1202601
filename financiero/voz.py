# -*- coding: utf-8 -*-
"""
Parser del asistente de voz — puro Python, sin Django ni BD.

Convierte una frase transcrita ("gasté 30 en menú y 10 en pasajes", "¿cuánto he
gastado este mes?", "gasto 50 soles ¿cuánto me queda?") en una estructura que
financiero/voz_servicios.py pueda aplicar contra la base de datos.

Diseño (regla del usuario: "todo gasto se relaciona con una categoría"):
  - Un ítem de GASTO sin categoría reconocida queda con campo=None y se marca
    como `faltante`: el pop-up debe preguntar la categoría antes de poder
    guardar nada — nunca se guarda un gasto suelto.
  - Un ítem de INGRESO sin tipo reconocido cae por defecto en 'ing_informal'
    (no bloquea), salvo que coincidan palabras de más de un tipo a la vez
    (ambiguo → si pregunta).
  - Para completar un dato que faltó, el llamador re-envía el texto nuevo
    CONCATENADO al `texto_normalizado` de la respuesta anterior (ver
    `interpretar(texto, contexto_previo=...)`) — no hay estado en el servidor.
"""
from __future__ import annotations

import re
import unicodedata

from financiero.voz_vocabulario import (
    CAMPOS_INGRESO,
    CATEGORIAS_GASTO,
    CENTENAS,
    DECENAS,
    DENOMINACIONES,
    PALABRAS_MES_PASADO,
    PALABRAS_MONEDA_EXTRANJERA,
    PALABRAS_PREGUNTA,
    PALABRAS_SIMULACION,
    SEPARADORES_ITEMS,
    UNIDADES,
    UNIDADES_MONEDA,
    VERBOS_GASTO,
    VERBOS_INGRESO,
)

MONTO_MAXIMO = 1_000_000  # tope de cordura; el servidor revalida igual


# ────────────────────────────────────────────────────────────────────────────
# Normalización de texto
# ────────────────────────────────────────────────────────────────────────────

def normalizar(texto: str) -> str:
    """minúsculas, sin tildes, 'S/'→'soles', '$'→'dolares', sin puntuación
    (salvo '.' y '/' dentro de números), comas tratadas como conector 'y'."""
    texto = (texto or '').lower().strip()
    texto = re.sub(r's\s*/\s*\.?(?=\s|\d|$)', ' soles ', texto)
    texto = texto.replace('$', ' dolares ')
    texto = unicodedata.normalize('NFKD', texto)
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    texto = texto.replace('¿', ' ').replace('?', ' ').replace('¡', ' ').replace('!', ' ')
    texto = re.sub(r'(\d),(\d)', r'\1.\2', texto)  # coma decimal -> punto
    texto = texto.replace(',', ' y ')
    texto = re.sub(r'[^\w\s.]', ' ', texto)
    texto = re.sub(r'\s+', ' ', texto).strip()
    return texto


# ────────────────────────────────────────────────────────────────────────────
# Números (dígitos y en palabras)
# ────────────────────────────────────────────────────────────────────────────

_RE_DIGITO = re.compile(r'^\d+(?:\.\d+)?$')
# Palabras que pueden formar parte de un número: unidades/decenas/centenas,
# "mil" y las denominaciones ("cheque", "ferro", "luca"...), que funcionan
# igual que "mil": multiplican lo acumulado (o valen 1 vez si van solas).
_PALABRAS_NUM = set(UNIDADES) | set(DECENAS) | set(CENTENAS) | set(DENOMINACIONES) | {'mil'}
_MULTIPLICADORES = {'mil': 1000, **DENOMINACIONES}


def _es_inicio_numero(tok: str, tokens: list[str], idx: int) -> bool:
    """True si `tok` puede empezar o continuar un número: un dígito, o una
    palabra numérica (con el caso especial de 'un/una/uno' sueltos, que solo
    cuentan si van pegados a una unidad monetaria o denominación — si no,
    "una recarga" se tomaría como monto 1)."""
    if _RE_DIGITO.fullmatch(tok):
        return True
    if tok in _PALABRAS_NUM:
        if tok in ('un', 'una', 'uno'):
            siguiente = tokens[idx + 1] if idx + 1 < len(tokens) else None
            return siguiente in UNIDADES_MONEDA or siguiente in DENOMINACIONES
        return True
    return False


def _evaluar_entero(palabras: list[str]):
    palabras = [p for p in palabras if p != 'y']
    if not palabras:
        return None
    total = 0.0
    actual = 0.0
    tuvo_valor = False
    for p in palabras:
        if _RE_DIGITO.fullmatch(p):
            actual += float(p)
            tuvo_valor = True
        elif p in _MULTIPLICADORES:
            # "mil", o una denominación ("cheque"=10, "ferro"=100...): si no
            # hay nada acumulado antes (ej. "cheque" solo), vale 1 vez.
            actual = actual if actual else 1
            total += actual * _MULTIPLICADORES[p]
            actual = 0
            tuvo_valor = True
        elif p in CENTENAS:
            actual += CENTENAS[p]
            tuvo_valor = True
        elif p in DECENAS:
            actual += DECENAS[p]
            tuvo_valor = True
        elif p in UNIDADES:
            actual += UNIDADES[p]
            tuvo_valor = True
        else:
            return None
    total += actual
    return total if tuvo_valor else None


def _evaluar_grupo_numerico(grupo: list[str]):
    if 'con' in grupo:
        i = grupo.index('con')
        entero = _evaluar_entero(grupo[:i])
        decimal = _evaluar_entero(grupo[i + 1:])
        if entero is None:
            return None
        if decimal is None:
            return float(entero)
        return round(float(entero) + (decimal % 100) / 100, 2)
    entero = _evaluar_entero(grupo)
    return float(entero) if entero is not None else None


def _extraer_todos_los_numeros(texto: str):
    """Reemplaza cada número (dígitos, en palabras o jerga como "20 cheques" =
    200) por un marcador 'num<k>'. Devuelve (texto_con_marcadores, [valores])."""
    tokens = texto.split()
    valores: list[float] = []
    out_tokens = []
    i = 0
    n = len(tokens)
    while i < n:
        t = tokens[i]
        if _es_inicio_numero(t, tokens, i):
            j = i
            while j + 1 < n and (
                _es_inicio_numero(tokens[j + 1], tokens, j + 1)
                or (tokens[j + 1] in ('y', 'con') and j + 2 < n
                    and _es_inicio_numero(tokens[j + 2], tokens, j + 2))
            ):
                j = j + 2 if tokens[j + 1] in ('y', 'con') else j + 1
            grupo = tokens[i:j + 1]
            valor = _evaluar_grupo_numerico(grupo)
            if valor is not None:
                valores.append(valor)
                out_tokens.append(f'num{len(valores) - 1}')
                i = j + 1
                continue
        out_tokens.append(t)
        i += 1
    return ' '.join(out_tokens), valores


# ────────────────────────────────────────────────────────────────────────────
# Búsqueda de palabras/frases (con límites de palabra)
# ────────────────────────────────────────────────────────────────────────────

def _contiene(texto: str, frase: str) -> bool:
    return re.search(r'\b' + re.escape(frase) + r'\b', texto) is not None


def _contiene_alguna(texto: str, frases) -> bool:
    return any(_contiene(texto, f) for f in frases)


def _contiene_raiz(texto: str, raiz: str) -> bool:
    """Como `_contiene`, pero solo exige límite de palabra AL INICIO: 'gast'
    encuentra 'gasto', 'gasté', 'gastando', 'gastado'... (no exige que la
    palabra termine justo ahí, a diferencia de `_contiene`)."""
    return re.search(r'\b' + re.escape(raiz), texto) is not None


def _contiene_o_plural(texto: str, frase: str) -> bool:
    """Como `_contiene`, pero acepta también el plural con 's' ("comida"/
    "comidas", "recibo"/"recibos"). Solo se usa para nombres de categoría/tipo
    de ingreso — los verbos y disparadores de pregunta siguen exactos con
    `_contiene`, donde una 's' de más sí cambiaría el sentido."""
    return re.search(r'\b' + re.escape(frase) + r's?\b', texto) is not None


def _detectar_categoria_gasto(texto: str):
    for campo, info in CATEGORIAS_GASTO.items():
        if any(_contiene_o_plural(texto, p) for p in info['palabras']):
            return campo
    return None


def _detectar_tipo_ingreso(texto: str):
    """Devuelve (campo|None, ambiguo: bool)."""
    coincidencias = [
        campo for campo, info in CAMPOS_INGRESO.items()
        if any(_contiene_o_plural(texto, p) for p in info['palabras'])
    ]
    if len(coincidencias) == 1:
        return coincidencias[0], False
    if len(coincidencias) > 1:
        return None, True
    return None, False


def _primer_num_en(texto: str, valores: list[float]):
    """Primer marcador NUM<k> que aparece en `texto`, o None."""
    m = re.search(r'\bnum(\d+)\b', texto)
    if not m:
        return None
    idx = int(m.group(1))
    return valores[idx] if idx < len(valores) else None


# ────────────────────────────────────────────────────────────────────────────
# Segmentación en ítems ("30 en menú y 10 en pasajes")
# ────────────────────────────────────────────────────────────────────────────

def _segmentar(texto_con_marcadores: str) -> list[str]:
    patron = r'\b(?:' + '|'.join(re.escape(s) for s in SEPARADORES_ITEMS) + r')\b'
    partes = re.split(patron, texto_con_marcadores)
    return [p.strip() for p in partes if p.strip()]


def _etiqueta_campo(tipo: str, campo: str) -> str:
    if tipo == 'gasto':
        return CATEGORIAS_GASTO[campo]['label']
    return CAMPOS_INGRESO[campo]['label']


def _procesar_segmento(segmento: str, valores: list[float], tipo_heredado):
    monto = _primer_num_en(segmento, valores)
    campo_gasto = _detectar_categoria_gasto(segmento)
    campo_ingreso, ambiguo = _detectar_tipo_ingreso(segmento)
    verbo_gasto = _contiene_alguna(segmento, VERBOS_GASTO)
    verbo_ingreso = _contiene_alguna(segmento, VERBOS_INGRESO)

    # Orden de prioridad importa: una palabra clave CONCRETA (campo_ingreso o
    # campo_gasto) pesa más que un verbo suelto. Esto resuelve el choque entre
    # "pago" (verbo de gasto: "pago 50 de luz") y la frase de ingreso "me
    # pago" (de "me pagó", sin tilde por la normalización — "mi jefe me pago
    # 200 de sueldo"): sin esta prioridad, la palabra "pago" dentro de "me
    # pago" también dispara verbo_gasto y gana por estar primero en el if/elif.
    if campo_ingreso or ambiguo:
        tipo = 'ingreso'
    elif campo_gasto:
        tipo = 'gasto'
    elif verbo_ingreso:
        tipo = 'ingreso'
    elif verbo_gasto:
        tipo = 'gasto'
    else:
        tipo = tipo_heredado

    if tipo is None:
        return None, tipo_heredado
    if tipo == 'gasto' and monto is None and not (campo_gasto and verbo_gasto):
        # Sin monto, hace falta categoría Y verbo de gasto A LA VEZ para asumir
        # que se quiere REGISTRAR. Uno solo no alcanza:
        #   - solo categoría ("¿cuánto me queda de transporte?") → pregunta.
        #   - solo verbo ("¿cuánto he gastado?", el mismo verbo sirve para
        #     preguntar y para declarar) → también pregunta.
        return None, tipo
    if tipo == 'ingreso' and monto is None and campo_ingreso is None and not ambiguo:
        # Verbo de ingreso solo (ej. "¿cuánto gané?"): sin monto ni tipo
        # reconocido no hay nada que registrar — probablemente es una pregunta.
        return None, tipo

    if tipo == 'gasto':
        item = {'tipo': 'gasto', 'campo': campo_gasto, 'monto': monto}
    else:
        item = {'tipo': 'ingreso', 'campo': campo_ingreso, 'monto': monto, 'ambiguo': ambiguo}
    return item, tipo


def _extraer_items(texto_con_marcadores: str, valores: list[float]) -> list[dict]:
    items = []
    tipo_heredado = None
    for seg in _segmentar(texto_con_marcadores):
        item, tipo_heredado = _procesar_segmento(seg, valores, tipo_heredado)
        if item:
            items.append(item)
    return items


# ────────────────────────────────────────────────────────────────────────────
# Preguntas / simulación / moneda extranjera / periodo
# ────────────────────────────────────────────────────────────────────────────

def _detectar_pregunta(texto: str) -> bool:
    return _contiene_alguna(texto, PALABRAS_PREGUNTA)


def _detectar_simulacion(texto: str) -> bool:
    return _contiene_alguna(texto, PALABRAS_SIMULACION)


def _detectar_moneda_extranjera(texto: str) -> bool:
    return _contiene_alguna(texto, PALABRAS_MONEDA_EXTRANJERA)


def _detectar_periodo(texto: str) -> str:
    return 'pasado' if _contiene_alguna(texto, PALABRAS_MES_PASADO) else 'actual'


def _es_comparacion(texto: str) -> bool:
    return _detectar_periodo(texto) == 'pasado' and _contiene_alguna(
        texto, ['mas que', 'menos que', 'comparado', 'igual que']
    )


def _extraer_consulta(texto: str):
    """Determina qué está preguntando el usuario. Devuelve un dict `consulta`."""
    periodo = _detectar_periodo(texto)

    if _es_comparacion(texto):
        return {'tipo': 'comparacion', 'campo': None, 'periodo': periodo}

    if _contiene_raiz(texto, 'cumpl') or _contiene_alguna(texto, ['voy bien', 'como voy']):
        return {'tipo': 'cumple_plan', 'campo': None, 'periodo': periodo}

    if _contiene_alguna(texto, ['en que gasto mas', 'en que categoria gasto mas', 'en que se me va la plata']):
        return {'tipo': 'top_categoria', 'campo': None, 'periodo': periodo}

    campo_categoria = _detectar_categoria_gasto(texto)

    if (_contiene_raiz(texto, 'queda') or _contiene_raiz(texto, 'sobra')
            or _contiene_raiz(texto, 'alcanz') or _contiene_raiz(texto, 'disponib')):
        return {'tipo': 'saldo_categoria', 'campo': campo_categoria, 'periodo': periodo}

    if campo_categoria and _contiene_raiz(texto, 'gast'):
        return {'tipo': 'gasto_categoria', 'campo': campo_categoria, 'periodo': periodo}

    if _contiene_raiz(texto, 'ahorr'):
        return {'tipo': 'ahorro', 'campo': None, 'periodo': periodo}

    if _contiene_raiz(texto, 'gan') or _contiene_raiz(texto, 'ingres') or _contiene_raiz(texto, 'cobr'):
        return {'tipo': 'ingreso_total', 'campo': None, 'periodo': periodo}

    return {'tipo': 'gasto_total', 'campo': None, 'periodo': periodo}


# ────────────────────────────────────────────────────────────────────────────
# Ejemplos dinámicos (para "no entendí" / falta un dato)
# ────────────────────────────────────────────────────────────────────────────

def _ejemplos_categoria(monto):
    m = int(monto) if monto and monto == int(monto) else monto
    ejemplo_monto = m if monto else 20
    return [
        f'gasté {ejemplo_monto} en transporte',
        f'gasté {ejemplo_monto} en comida',
    ]


def _ejemplos_monto(campo):
    etiqueta = CATEGORIAS_GASTO.get(campo, {}).get('label', 'transporte').lower()
    return [f'20 en {etiqueta}', f'gasté 20 en {etiqueta}']


def _ejemplos_generales():
    return [
        'gasté 20 en taxi',
        '¿cuánto he gastado este mes?',
        '¿cuánto me queda en comida?',
    ]


# ────────────────────────────────────────────────────────────────────────────
# Punto de entrada
# ────────────────────────────────────────────────────────────────────────────

def interpretar(texto: str, contexto_previo: str = '') -> dict:
    """Interpreta una frase dictada/escrita. `contexto_previo` es el
    `texto_normalizado` de una respuesta anterior con `faltante` (se
    concatena para resolver el dato que faltaba con la nueva frase)."""
    texto_actual = normalizar(texto)
    texto_completo = f'{contexto_previo} {texto_actual}'.strip() if contexto_previo else texto_actual

    if _detectar_moneda_extranjera(texto_completo):
        return {
            'intencion': 'moneda_no_soportada',
            'texto_normalizado': texto_completo,
            'mensaje': 'Por ahora solo registramos montos en soles.',
        }

    texto_marcado, valores = _extraer_todos_los_numeros(texto_completo)
    items = _extraer_items(texto_marcado, valores)

    # Resolver items: aplicar defaults de ingreso, validar montos y detectar faltantes.
    items_completos = []
    faltante = None
    for it in items:
        monto = it.get('monto')
        if monto is not None and (monto <= 0 or monto > MONTO_MAXIMO):
            monto = None
            it['monto'] = None

        if it['tipo'] == 'gasto':
            if it['campo'] is None:
                faltante = faltante or {'tipo': 'categoria', 'monto': monto, 'item_tipo': 'gasto'}
                continue
            if monto is None:
                faltante = faltante or {'tipo': 'monto', 'campo': it['campo'], 'item_tipo': 'gasto'}
                continue
            items_completos.append({
                'tipo': 'gasto', 'campo': it['campo'],
                'etiqueta': _etiqueta_campo('gasto', it['campo']),
                'monto': round(monto, 2),
            })
        else:  # ingreso
            if it.get('ambiguo'):
                faltante = faltante or {'tipo': 'tipo_ingreso', 'monto': monto, 'item_tipo': 'ingreso'}
                continue
            campo = it['campo'] or 'ing_informal'
            if monto is None:
                faltante = faltante or {'tipo': 'monto', 'campo': campo, 'item_tipo': 'ingreso'}
                continue
            items_completos.append({
                'tipo': 'ingreso', 'campo': campo,
                'etiqueta': _etiqueta_campo('ingreso', campo),
                'monto': round(monto, 2),
            })

    es_pregunta = _detectar_pregunta(texto_completo)
    es_simulacion = _detectar_simulacion(texto_completo)
    hay_registro = bool(items_completos) or faltante is not None

    consulta = None
    if es_pregunta or es_simulacion:
        consulta = _extraer_consulta(texto_completo)
        # Si la pregunta es sobre "cuánto me queda" sin categoría explícita pero
        # hay un gasto en curso (mixta), la categoría del gasto resuelve la consulta.
        if consulta['campo'] is None and items_completos and consulta['tipo'] == 'saldo_categoria':
            consulta['campo'] = items_completos[-1]['campo']

    if es_simulacion and hay_registro:
        intencion = 'simulacion'
    elif es_pregunta and hay_registro:
        intencion = 'mixta'
    elif faltante is not None:
        intencion = 'gasto' if faltante['item_tipo'] == 'gasto' else 'ingreso'
        intencion = 'registrar'  # queda incompleto; el llamador mira `faltante`
    elif items_completos:
        intencion = 'registrar'
    elif es_pregunta:
        intencion = 'consultar'
    else:
        intencion = 'desconocida'

    if faltante and faltante['tipo'] == 'categoria':
        ejemplos = _ejemplos_categoria(faltante.get('monto'))
    elif faltante and faltante['tipo'] == 'monto':
        ejemplos = _ejemplos_monto(faltante.get('campo'))
    elif intencion == 'desconocida':
        ejemplos = _ejemplos_generales()
    else:
        ejemplos = []

    return {
        'intencion': intencion,
        'items': items_completos,
        'faltante': faltante,
        'consulta': consulta,
        'ejemplos': ejemplos,
        'texto_normalizado': texto_completo,
    }
