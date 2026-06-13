/* SIGAMOS — Utilidades JS compartidas */

// ===== TOAST =====
function showToast(msg, tipo = 'info') {
  const t = document.getElementById('toast');
  if (!t) return;
  t.textContent = msg;
  t.className = 'toast show';
  setTimeout(() => t.classList.remove('show'), 3500);
}

// ===== MODAL =====
function openModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.add('open');
}
function closeModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.remove('open');
}
document.addEventListener('click', e => {
  if (e.target.classList.contains('modal-overlay')) {
    e.target.classList.remove('open');
  }
});

// ===== CHART DEFAULTS =====
const SIGAMOS_COLORS = {
  blue: 'rgba(59,130,246,',
  green: 'rgba(16,185,129,',
  orange: 'rgba(245,158,11,',
  purple: 'rgba(139,92,246,',
  red: 'rgba(239,68,68,',
  pink: 'rgba(236,72,153,',
};

const chartDefaults = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: {
      labels: {
        font: { family: 'Segoe UI', size: 12 },
        color: '#64748b',
        boxWidth: 12,
      }
    }
  },
};

function mkBar(canvasId, labels, ingresos, gastos) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return null;
  return new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        { label: 'Ingresos', data: ingresos, backgroundColor: 'rgba(16,185,129,.75)', borderRadius: 6, borderSkipped: false },
        { label: 'Gastos', data: gastos, backgroundColor: 'rgba(59,130,246,.75)', borderRadius: 6, borderSkipped: false },
      ]
    },
    options: {
      ...chartDefaults,
      scales: {
        x: { grid: { display: false }, ticks: { color: '#94a3b8' } },
        y: { grid: { color: 'rgba(0,0,0,.04)' }, ticks: { color: '#94a3b8', callback: v => 'S/ ' + v.toLocaleString('es-PE') } }
      }
    }
  });
}

function mkDoughnut(canvasId, labels, data) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return null;
  const bg = [
    'rgba(59,130,246,.8)', 'rgba(16,185,129,.8)', 'rgba(245,158,11,.8)',
    'rgba(139,92,246,.8)', 'rgba(239,68,68,.8)', 'rgba(236,72,153,.8)',
    'rgba(14,165,233,.8)', 'rgba(168,85,247,.8)',
  ];
  return new Chart(ctx, {
    type: 'doughnut',
    data: { labels, datasets: [{ data, backgroundColor: bg, borderWidth: 0, hoverOffset: 6 }] },
    options: {
      ...chartDefaults,
      cutout: '65%',
      plugins: { ...chartDefaults.plugins, legend: { position: 'right', labels: { ...chartDefaults.plugins.legend.labels } } }
    }
  });
}

function mkLine(canvasId, labels, data, label = 'Valor', color = 'rgba(59,130,246,') {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return null;
  return new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label,
        data,
        borderColor: color + '1)',
        backgroundColor: color + '.1)',
        borderWidth: 2.5,
        fill: true,
        tension: 0.4,
        pointBackgroundColor: color + '1)',
        pointRadius: 4,
      }]
    },
    options: {
      ...chartDefaults,
      scales: {
        x: { grid: { display: false }, ticks: { color: '#94a3b8' } },
        y: { grid: { color: 'rgba(0,0,0,.04)' }, ticks: { color: '#94a3b8', callback: v => 'S/ ' + v.toLocaleString('es-PE') } }
      }
    }
  });
}

function mkHorizontalBar(canvasId, labels, data, label = 'Impacto SHAP') {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return null;
  const colors = data.map(v => v >= 0 ? 'rgba(239,68,68,.75)' : 'rgba(16,185,129,.75)');
  return new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{ label, data, backgroundColor: colors, borderRadius: 4, borderSkipped: false }]
    },
    options: {
      ...chartDefaults,
      indexAxis: 'y',
      scales: {
        x: { grid: { color: 'rgba(0,0,0,.04)' }, ticks: { color: '#94a3b8' } },
        y: { grid: { display: false }, ticks: { color: '#64748b', font: { size: 12 } } }
      }
    }
  });
}

// ===== CSRF helper para fetch() =====
function getCookie(name) {
  let value = null;
  document.cookie.split(';').forEach(c => {
    const [k, v] = c.trim().split('=');
    if (k === name) value = decodeURIComponent(v);
  });
  return value;
}

const csrfToken = getCookie('csrftoken');
