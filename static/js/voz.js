// ===== ASISTENTE DE VOZ ("🎤 Habla con SmartSave") =====
// Registrar ingresos/gastos y preguntar por el estado financiero, por voz o
// texto. Consume /api/v1/voz/interpretar|confirmar|deshacer/ (financiero/voz.py
// + financiero/voz_servicios.py). Reutiliza openModal/closeModal, showToast y
// csrfToken de sigamos.js (debe cargarse antes que este archivo).

const CATEGORIAS_GASTO_VOZ = [
  { campo: 'gasto_alimentos', etiqueta: 'Alimentos', icono: '🍔' },
  { campo: 'gasto_vestido', etiqueta: 'Ropa', icono: '👗' },
  { campo: 'gasto_vivienda_servicios', etiqueta: 'Vivienda y servicios', icono: '🏠' },
  { campo: 'gasto_salud', etiqueta: 'Salud', icono: '💊' },
  { campo: 'gasto_transporte', etiqueta: 'Transporte', icono: '🚌' },
  { campo: 'gasto_comunicaciones', etiqueta: 'Comunicaciones', icono: '📱' },
  { campo: 'gasto_educacion', etiqueta: 'Educación', icono: '🎓' },
  { campo: 'gasto_otros_bienes', etiqueta: 'Otros gastos', icono: '🛒' },
];
const TIPOS_INGRESO_VOZ = [
  { campo: 'ing_planilla', etiqueta: 'Ingreso en planilla', icono: '💰' },
  { campo: 'bonif_monto', etiqueta: 'Bonificación', icono: '🎁' },
  { campo: 'ing_informal', etiqueta: 'Ingreso informal', icono: '💰' },
];

const vozState = {
  contextoPrevio: '',
  reconocimiento: null,
  soportaVoz: !!(window.SpeechRecognition || window.webkitSpeechRecognition),
  silenciado: false,
};

try {
  vozState.silenciado = localStorage.getItem('voz_silenciado') === '1';
} catch (e) { /* localStorage puede fallar en modo privado; no es crítico */ }

function _vozContenido() {
  return document.getElementById('voz-contenido');
}

// El texto dictado/escrito por el propio usuario (texto_normalizado) y las
// respuestas se insertan con innerHTML: se escapan para que no se interpreten
// como HTML si alguien escribe/dice algo con "<" o similares (modo texto).
function _vozEscapeHtml(texto) {
  const div = document.createElement('div');
  div.textContent = texto == null ? '' : String(texto);
  return div.innerHTML;
}

function abrirAsistenteVoz() {
  vozState.contextoPrevio = '';
  openModal('modal-voz');
  if (vozState.soportaVoz) {
    vozVistaEscuchando();
    vozEscuchar();
  } else {
    vozVistaSinSoporte('Tu navegador no tiene reconocimiento de voz. Escribe lo que quieres registrar o preguntar:');
  }
}

const VOZ_MAX_MS = 60000; // 1 minuto máximo escuchando

function cerrarAsistenteVoz(recargar) {
  clearTimeout(vozState.timeoutMaximo);
  if (vozState.reconocimiento) {
    vozState.cancelado = true;
    try { vozState.reconocimiento.abort(); } catch (e) { /* ya estaba detenido */ }
  }
  window.speechSynthesis && window.speechSynthesis.cancel();
  closeModal('modal-voz');
  if (recargar) location.reload();
}

// ── Reconocimiento de voz ──────────────────────────────────────────────────
// `continuous:true` para que NO se corte solo tras la primera pausa (antes
// tomaba una sola frase y listo); el usuario dice todo lo que necesite, hasta
// VOZ_MAX_MS (1 minuto), y pulsa "Terminé de hablar" (vozDetenerEscucha) o
// espera a que se corte solo al llegar al máximo.

function vozEscuchar() {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const rec = new Recognition();
  rec.lang = 'es-PE';
  rec.continuous = true;
  rec.interimResults = true;
  rec.maxAlternatives = 1;
  vozState.reconocimiento = rec;
  vozState.textoAcumulado = '';
  vozState.cancelado = false;
  let errorFatal = false;

  vozState.timeoutMaximo = setTimeout(() => {
    showToast('Llegaste al máximo de 1 minuto grabando.');
    vozDetenerEscucha();
  }, VOZ_MAX_MS);

  rec.onresult = (ev) => {
    let texto = '';
    for (let i = 0; i < ev.results.length; i++) texto += ev.results[i][0].transcript;
    vozState.textoAcumulado = texto;
    const parcial = document.getElementById('voz-parcial');
    if (parcial) parcial.textContent = texto;
  };
  rec.onerror = (ev) => {
    if (ev.error === 'aborted') return; // el usuario cerró/canceló el modal
    if (ev.error === 'not-allowed' || ev.error === 'service-not-allowed') {
      errorFatal = true;
      vozVistaSinSoporte('No se pudo usar el micrófono (permiso denegado). Escribe lo que quieres registrar o preguntar:');
      return;
    }
    // 'no-speech' y demás: se resuelven en onend según si ya quedó algo dicho.
  };
  rec.onend = () => {
    clearTimeout(vozState.timeoutMaximo);
    vozState.reconocimiento = null;
    if (errorFatal || vozState.cancelado) return;
    const texto = (vozState.textoAcumulado || '').trim();
    if (!texto) {
      vozVistaNoEntendido({ texto_normalizado: '', ejemplos: [] });
      return;
    }
    vozProcesarTexto(texto);
  };
  try {
    rec.start();
  } catch (e) {
    clearTimeout(vozState.timeoutMaximo);
    vozVistaSinSoporte('No se pudo iniciar el micrófono. Escribe lo que quieres registrar o preguntar:');
  }
}

function vozDetenerEscucha() {
  clearTimeout(vozState.timeoutMaximo);
  if (vozState.reconocimiento) {
    try { vozState.reconocimiento.stop(); } catch (e) { /* ya estaba detenido */ }
  }
}

// ── Llamadas a la API ───────────────────────────────────────────────────────

function _vozFetch(url, data) {
  return fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
    credentials: 'same-origin',
    body: JSON.stringify(data),
  }).then(async (r) => {
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw { status: r.status, body };
    return body;
  });
}

function vozProcesarTexto(texto) {
  vozVistaProcesando();
  _vozFetch('/api/v1/voz/interpretar/', { texto, contexto_previo: vozState.contextoPrevio })
    .then((resultado) => {
      vozState.contextoPrevio = resultado.texto_normalizado || '';
      vozRenderizar(resultado);
    })
    .catch(() => {
      showToast('No se pudo interpretar lo dicho. Intenta de nuevo.');
      vozVistaEscuchando();
    });
}

function vozConfirmar(items) {
  vozVistaProcesando();
  _vozFetch('/api/v1/voz/confirmar/', { items })
    .then((resultado) => vozVistaExito(resultado))
    .catch((err) => {
      const msg = (err.body && (err.body.error || JSON.stringify(err.body))) || 'No se pudo guardar.';
      showToast(msg);
      vozVistaConfirmar(
        { items, intencion: 'registrar', texto_normalizado: vozState.contextoPrevio },
        { tiene_plan: false, impacto_plan: [], excede_plan: false, compensar_con: [] },
      );
    });
}

function vozDeshacer(token, btn) {
  if (btn) { btn.disabled = true; btn.textContent = 'Deshaciendo…'; }
  _vozFetch('/api/v1/voz/deshacer/', { token })
    .then(() => {
      showToast('Registro deshecho.');
      cerrarAsistenteVoz(true);
    })
    .catch((err) => {
      showToast((err.body && err.body.error) || 'No se pudo deshacer.');
      if (btn) { btn.disabled = false; btn.textContent = 'Deshacer'; }
    });
}

// ── Dispatcher de vistas según la respuesta de /interpretar/ ───────────────

function vozRenderizar(resultado) {
  if (resultado.intencion === 'moneda_no_soportada') {
    vozVistaMensaje('💱', resultado.mensaje, true);
    return;
  }
  if (resultado.faltante) {
    vozVistaFaltante(resultado);
    return;
  }
  if (resultado.items && resultado.items.length) {
    vozVistaConfirmar(resultado, resultado.previsualizacion);
    return;
  }
  if (resultado.intencion === 'consultar' && resultado.respuesta) {
    vozVistaRespuesta(resultado);
    return;
  }
  vozVistaNoEntendido(resultado);
}

// ── Vistas ──────────────────────────────────────────────────────────────────

function vozVistaEscuchando() {
  _vozContenido().innerHTML = `
    <div class="voz-escuchando">
      <div class="voz-mic-pulso">🎤</div>
      <div class="voz-estado-texto">Escuchando… di todo lo que necesites</div>
      <div class="text-xs text-muted mt-1">Máximo 1 minuto</div>
      <div id="voz-parcial" class="voz-parcial"></div>
    </div>
    <button type="button" class="btn btn-primary btn-voz-detener" onclick="vozDetenerEscucha()">⏹ Terminé de hablar</button>
    <div class="modal-actions">
      <button type="button" class="btn btn-outline btn-sm" onclick="vozVistaSinSoporte('Escribe lo que quieres registrar o preguntar:')">✍️ Escribir en vez de hablar</button>
      <button type="button" class="btn btn-outline btn-sm" onclick="cerrarAsistenteVoz(false)">Cancelar</button>
    </div>`;
}

function vozVistaProcesando() {
  _vozContenido().innerHTML = `
    <div class="voz-escuchando">
      <div class="voz-mic-pulso">⏳</div>
      <div class="voz-estado-texto">Pensando…</div>
    </div>`;
}

function vozVistaSinSoporte(mensaje) {
  _vozContenido().innerHTML = `
    <p class="text-sm text-muted mb-4">${mensaje}</p>
    <div class="form-group">
      <input type="text" class="form-input" id="voz-input-texto" placeholder="Ej: gasté 20 en taxi"
             onkeydown="if(event.key==='Enter'){vozEnviarTexto();}">
    </div>
    <div class="modal-actions">
      <button type="button" class="btn btn-outline btn-sm" onclick="cerrarAsistenteVoz(false)">Cancelar</button>
      <button type="button" class="btn btn-primary btn-sm" onclick="vozEnviarTexto()">Enviar</button>
    </div>`;
  const input = document.getElementById('voz-input-texto');
  if (input) input.focus();
}

function vozEnviarTexto() {
  const input = document.getElementById('voz-input-texto');
  const texto = input ? input.value.trim() : '';
  if (!texto) return;
  vozProcesarTexto(texto);
}

function vozVistaMensaje(icono, texto, permitirReintentar) {
  _vozContenido().innerHTML = `
    <div class="voz-escuchando">
      <div class="voz-mic-pulso" style="animation:none;">${icono}</div>
      <div class="voz-estado-texto">${texto}</div>
    </div>
    <div class="modal-actions">
      ${permitirReintentar ? '<button type="button" class="btn btn-outline btn-sm" onclick="vozState.contextoPrevio=\'\';vozVistaEscuchando();vozEscuchar();">🎤 Intentar de nuevo</button>' : ''}
      <button type="button" class="btn btn-primary btn-sm" onclick="cerrarAsistenteVoz(false)">Cerrar</button>
    </div>`;
}

function vozVistaNoEntendido(resultado) {
  const ejemplos = (resultado.ejemplos || []).map((e) => `<li>"${_vozEscapeHtml(e)}"</li>`).join('');
  const escuchado = resultado.texto_normalizado
    ? `<p class="text-sm mb-2">Escuché: <em>"${_vozEscapeHtml(resultado.texto_normalizado)}"</em></p>` : '';
  _vozContenido().innerHTML = `
    <div class="voz-escuchando">
      <div class="voz-mic-pulso" style="animation:none;">🤔</div>
      <div class="voz-estado-texto">No entendí eso</div>
    </div>
    ${escuchado}
    ${ejemplos ? `<p class="text-sm text-muted mb-1">Prueba con algo como:</p><ul class="text-sm text-muted" style="padding-left:18px;">${ejemplos}</ul>` : ''}
    <div class="modal-actions">
      <button type="button" class="btn btn-outline btn-sm" onclick="vozState.contextoPrevio='';vozVistaSinSoporte('Escribe lo que quieres registrar o preguntar:')">✍️ Escribir</button>
      <button type="button" class="btn btn-primary btn-sm" onclick="vozState.contextoPrevio='';vozVistaEscuchando();vozEscuchar();">🎤 Intentar de nuevo</button>
    </div>`;
}

function vozVistaFaltante(resultado) {
  const f = resultado.faltante;
  let cuerpo = '';
  if (f.tipo === 'categoria') {
    const chips = CATEGORIAS_GASTO_VOZ.map((c) => `
      <button type="button" class="btn btn-outline btn-sm voz-chip" onclick="vozProcesarTexto('${c.etiqueta}')">${c.icono} ${c.etiqueta}</button>
    `).join('');
    cuerpo = `
      <p class="text-sm mb-3">Entendí S/ ${(f.monto || 0).toFixed(2)}. ¿En qué categoría lo gastaste?</p>
      <div class="voz-chips">${chips}</div>`;
  } else if (f.tipo === 'tipo_ingreso') {
    // No se re-interpreta la frase: si fue ambigua (ej. "sueldo y bono" a la
    // vez), concatenar la respuesta no la desambigua porque ambas palabras
    // siguen presentes. Se arma el ítem directo y se va a confirmar/guardar.
    const chips = TIPOS_INGRESO_VOZ.map((c) => `
      <button type="button" class="btn btn-outline btn-sm voz-chip"
              onclick="vozResolverTipoIngreso('${c.campo}', '${c.etiqueta}', ${f.monto || 0})">${c.icono} ${c.etiqueta}</button>
    `).join('');
    cuerpo = `
      <p class="text-sm mb-3">Entendí un ingreso de S/ ${(f.monto || 0).toFixed(2)}. ¿De qué tipo es?</p>
      <div class="voz-chips">${chips}</div>`;
  } else {
    const etiqueta = _vozEtiquetaCampo(f.campo);
    cuerpo = `
      <p class="text-sm mb-3">Entendí ${etiqueta}. ¿Cuánto fue?</p>
      <div class="form-row cols-2">
        <input type="number" min="0.01" step="0.01" class="form-input" id="voz-input-monto" placeholder="Monto en soles"
               onkeydown="if(event.key==='Enter'){vozEnviarMonto();}">
        <button type="button" class="btn btn-primary btn-sm" onclick="vozEnviarMonto()">Registrar</button>
      </div>`;
  }
  // vozState.contextoPrevio ya trae el texto acumulado (lo fija vozProcesarTexto
  // antes de llamar a esta vista), así que re-escuchar sigue completando la misma
  // frase en vez de empezar de cero.
  _vozContenido().innerHTML = `
    ${cuerpo}
    <div class="modal-actions">
      <button type="button" class="btn btn-outline btn-sm" onclick="vozVistaEscuchando();vozEscuchar();">🎤 Decirlo</button>
      <button type="button" class="btn btn-outline btn-sm" onclick="cerrarAsistenteVoz(false)">Cancelar</button>
    </div>
    <p class="text-xs text-muted mt-3" style="text-align:center;">
      ¿Se quedó atascado? <a href="#" onclick="vozState.contextoPrevio='';vozVistaEscuchando();vozEscuchar();return false;">Empezar de nuevo</a>
    </p>`;
}

function vozResolverTipoIngreso(campo, etiqueta, monto) {
  if (!monto || monto <= 0) {
    // Caso raro: ambiguo Y sin monto a la vez. Se pide de nuevo desde cero,
    // ya con el tipo aclarado, en vez de arrastrar un texto contradictorio.
    vozState.contextoPrevio = '';
    vozProcesarTexto(`${monto || ''} ${etiqueta}`.trim());
    return;
  }
  vozVistaConfirmar(
    {
      intencion: 'registrar',
      items: [{ tipo: 'ingreso', campo, etiqueta, monto }],
      respuesta: null,
      texto_normalizado: vozState.contextoPrevio,
    },
    null,
  );
}

function vozEnviarMonto() {
  const input = document.getElementById('voz-input-monto');
  const valor = input ? input.value.trim() : '';
  if (!valor || parseFloat(valor) <= 0) { showToast('Ingresa un monto válido.'); return; }
  vozProcesarTexto(valor);
}

function _vozEtiquetaCampo(campo) {
  const todos = CATEGORIAS_GASTO_VOZ.concat(TIPOS_INGRESO_VOZ);
  const found = todos.find((c) => c.campo === campo);
  return found ? `${found.icono} ${found.etiqueta}` : campo;
}

function vozVistaConfirmar(resultado, previsualizacion) {
  const esSimulacion = resultado.intencion === 'simulacion';
  const items = resultado.items;
  const filasItems = items.map((it, idx) => {
    const opciones = (it.tipo === 'gasto' ? CATEGORIAS_GASTO_VOZ : TIPOS_INGRESO_VOZ)
      .map((c) => `<option value="${c.campo}" ${c.campo === it.campo ? 'selected' : ''}>${c.icono} ${c.etiqueta}</option>`)
      .join('');
    return `
      <div class="form-row cols-2 mb-2" data-item-idx="${idx}" data-item-tipo="${it.tipo}">
        <select class="form-input voz-item-campo">${opciones}</select>
        <input type="number" min="0.01" step="0.01" class="form-input voz-item-monto" value="${it.monto}">
      </div>`;
  }).join('');

  let impactoHtml = '';
  if (previsualizacion && previsualizacion.tiene_plan && previsualizacion.impacto_plan.length) {
    const tarjetas = previsualizacion.impacto_plan
      .filter((f) => f.tocada)
      .map((f) => `
        <div class="budget-card ${f.excedido ? 'over' : 'ok'}">
          <div class="budget-card-head">
            <span class="budget-card-icon">${f.icono}</span>
            <span class="budget-card-name">${f.categoria}</span>
            ${f.excedido
              ? `<span class="badge badge-orange" style="margin-left:auto;">+S/ ${f.excedente.toFixed(0)}</span>`
              : '<span class="badge badge-green" style="margin-left:auto;">✓ en presupuesto</span>'}
          </div>
          <div class="progress-bar budget-bar ${f.excedido ? 'over-bar' : ''} mt-2">
            <div class="progress-fill" style="width:${f.pct_barra}%;"></div>
          </div>
          <div class="budget-card-amounts">
            <span>S/ ${f.gastado.toFixed(0)} gastado</span>
            <span class="text-muted">de S/ ${f.sugerido.toFixed(0)}</span>
          </div>
        </div>`).join('');
    // En vez del aviso "te pasarías de tu plan" (podía sonar a error del
    // sistema), se muestra la transcripción tal cual se entendió: así el
    // usuario revisa si el exceso viene de algo mal reconocido antes de
    // confirmar. Las tarjetas de abajo ya muestran igual qué categoría se
    // pasó y cuánto, así que no se pierde esa información.
    let aviso = '';
    if (previsualizacion.excede_plan && resultado.texto_normalizado) {
      aviso = `<p class="text-xs text-muted mb-3">🎤 Escuché: <em>"${_vozEscapeHtml(resultado.texto_normalizado)}"</em></p>`;
    }
    impactoHtml = `
      <div class="text-xs text-muted mb-2 mt-3">Así quedaría tu plan de ahorro:</div>
      ${aviso}
      <div class="budget-grid mb-3">${tarjetas}</div>`;
  } else if (previsualizacion && !previsualizacion.tiene_plan) {
    impactoHtml = '';
  }

  const respuestaHtml = resultado.respuesta
    ? `<div class="text-xs text-muted mb-3">📊 ${_vozEscapeHtml(resultado.respuesta.texto)}</div>` : '';

  _vozContenido().innerHTML = `
    <p class="text-sm mb-3">Esto entendí${esSimulacion ? ' (simulación, no se guarda todavía)' : ''}:</p>
    <div id="voz-items">${filasItems}</div>
    ${respuestaHtml}
    ${impactoHtml}
    <div class="modal-actions">
      <button type="button" class="btn btn-outline btn-sm" onclick="cerrarAsistenteVoz(false)">Cancelar</button>
      <button type="button" class="btn btn-primary btn-sm" onclick="vozConfirmarDesdeFormulario()">
        ${esSimulacion ? '✅ Registrarlo' : '✅ Confirmar'}
      </button>
    </div>`;
}

function vozConfirmarDesdeFormulario() {
  const filas = document.querySelectorAll('#voz-items [data-item-idx]');
  const items = Array.from(filas).map((fila) => {
    const tipo = fila.getAttribute('data-item-tipo');
    const campo = fila.querySelector('.voz-item-campo').value;
    const monto = parseFloat(fila.querySelector('.voz-item-monto').value);
    const etiqueta = _vozEtiquetaCampo(campo).replace(/^\S+\s/, '');
    return { tipo, campo, etiqueta, monto };
  });
  if (items.some((it) => !it.monto || it.monto <= 0)) {
    showToast('Revisa los montos: deben ser mayores a 0.');
    return;
  }
  vozConfirmar(items);
}

function vozVistaExito(resultado) {
  const filas = resultado.items.map((it) => `<li>${it.etiqueta}: S/ ${it.monto.toFixed(2)}</li>`).join('');
  const logros = resultado.logros_nuevos && resultado.logros_nuevos.length
    ? `<div class="info-box mb-3">🎉 ¡Desbloqueaste ${resultado.logros_nuevos.length} logro${resultado.logros_nuevos.length > 1 ? 's' : ''} nuevo${resultado.logros_nuevos.length > 1 ? 's' : ''}! <a href="/gamificacion/logros/" style="font-weight:700;">Ver logros →</a></div>`
    : '';
  const invitacionPlan = !resultado.tiene_plan
    ? `<div class="warning-box mb-3"><span>💡</span><p>Aún no tienes un plan de ahorro. <a href="/recomendaciones/" style="font-weight:700;">Generar mi plan →</a></p></div>`
    : '';
  _vozContenido().innerHTML = `
    <div class="voz-escuchando">
      <div class="voz-mic-pulso" style="animation:none;">✅</div>
      <div class="voz-estado-texto">¡Listo!</div>
    </div>
    <ul class="text-sm mb-3" style="padding-left:18px;">${filas}</ul>
    ${logros}
    ${invitacionPlan}
    <div class="modal-actions">
      <button type="button" class="btn btn-outline btn-sm" id="voz-btn-deshacer" onclick="vozDeshacer('${resultado.token_deshacer}', this)">Deshacer</button>
      <button type="button" class="btn btn-primary btn-sm" onclick="cerrarAsistenteVoz(true)">Cerrar</button>
    </div>`;
}

function vozVistaRespuesta(resultado) {
  const r = resultado.respuesta;
  let detalleHtml = '';
  if (r.detalle && typeof r.detalle === 'object' && !Array.isArray(r.detalle)) {
    const filas = Object.entries(r.detalle)
      .filter(([, v]) => typeof v === 'number' && v > 0)
      .map(([k, v]) => `<li>${k}: S/ ${v.toFixed(2)}</li>`).join('');
    if (filas) detalleHtml = `<ul class="text-sm text-muted mb-3" style="padding-left:18px;">${filas}</ul>`;
  }
  _vozContenido().innerHTML = `
    <div class="voz-escuchando">
      <div class="voz-mic-pulso" style="animation:none;">💬</div>
      <div class="voz-estado-texto">${_vozEscapeHtml(r.texto)}</div>
    </div>
    ${detalleHtml}
    <div class="modal-actions">
      <button type="button" class="btn btn-outline btn-sm" onclick="vozToggleSilencio(this)">${vozState.silenciado ? '🔇' : '🔊'}</button>
      <button type="button" class="btn btn-outline btn-sm" onclick="vozState.contextoPrevio='';vozVistaEscuchando();vozEscuchar();">🎤 Otra pregunta</button>
      <button type="button" class="btn btn-primary btn-sm" onclick="cerrarAsistenteVoz(false)">Cerrar</button>
    </div>`;
  vozHablar(r.texto);
}

function vozToggleSilencio(btn) {
  vozState.silenciado = !vozState.silenciado;
  try { localStorage.setItem('voz_silenciado', vozState.silenciado ? '1' : '0'); } catch (e) { /* no crítico */ }
  if (vozState.silenciado) { window.speechSynthesis && window.speechSynthesis.cancel(); }
  btn.textContent = vozState.silenciado ? '🔇' : '🔊';
}

function vozHablar(texto) {
  if (vozState.silenciado || !window.speechSynthesis) return;
  try {
    const u = new SpeechSynthesisUtterance(texto);
    u.lang = 'es-PE';
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(u);
  } catch (e) { /* sintesis de voz no disponible; el texto ya se muestra igual */ }
}

document.addEventListener('DOMContentLoaded', () => {
  const btn = document.getElementById('btn-asistente-voz');
  if (btn) btn.addEventListener('click', abrirAsistenteVoz);
});
