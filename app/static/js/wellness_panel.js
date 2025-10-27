/* FILE: static/js/wellness_panel.js
   Kushwell Wellness: Quick Check-in + Half-Donut QoL Gauge (+ optional line chart)
*/{% extends "base.html" %}
{% block title %}Wellness Details{% endblock %}
{% block body_class %}theme-chalk{% endblock %}
{% block head_extra %}
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.2/dist/chart.umd.min.js" defer></script>
  <script src="{{ url_for('static', filename='js/wellness_panel.js') }}?v=4" defer></script>
{% endblock %}
{% block content %}

  <section class="card card-large">
    <div class="card-front">
      <h3>Wellness Over Time</h3>
      <div class="kush-card" style="height:260px;">
        <canvas id="wellnessOverTime" aria-label="QoL over time"></canvas>
        <script id="wellness-history" type="application/json">
          {{ wellness_history_json | tojson }}
        </script>
      </div>

      <div class="kush-card" style="margin-top:.9rem;">
        <h4 style="margin:.2rem 0 .6rem;">Quick Check-in</h4>
        <form id="wellness-form" data-post-url="{{ url_for('patient.wellness_checkin') }}">
          <label for="pain">Pain (1â€“10, 10 = worst)</label>
          <input id="pain" name="pain_level" type="range" min="1" max="10" step="1" value="{{ last_levels.pain }}">

          <label for="mood">Mood (1â€“10)</label>
          <input id="mood" name="mood_level" type="range" min="1" max="10" step="1" value="{{ last_levels.mood }}">

          <label for="energy">Energy (1â€“10)</label>
          <input id="energy" name="energy_level" type="range" min="1" max="10" step="1" value="{{ last_levels.energy }}">

          <label for="clarity">Clarity (1â€“10)</label>
          <input id="clarity" name="clarity_level" type="range" min="1" max="10" step="1" value="{{ last_levels.clarity }}">

          <label for="appetite">Appetite (1â€“10)</label>
          <input id="appetite" name="appetite_level" type="range" min="1" max="10" step="1" value="{{ last_levels.appetite }}">

          <div style="margin-top:.6rem;">
            <button type="submit" class="kw-btn primary">Save Check-in</button>
            <span class="kush-muted" id="wellness-save-status"></span>
          </div>
        </form>
      </div>

      <div class="kush-card" style="margin-top:.9rem;">
        <h4 style="margin:.2rem 0 .6rem;">Score by dimension</h4>
        <table class="kw-table" aria-label="QoL contribution by dimension">
          <thead><tr><th>Dimension</th><th>Contribution (0â€“20)</th></tr></thead>
          <tbody>
            <tr><td>Pain (inverted)</td><td>{{ contributions.pain }}</td></tr>
            <tr><td>Mood</td><td>{{ contributions.mood }}</td></tr>
            <tr><td>Energy</td><td>{{ contributions.energy }}</td></tr>
            <tr><td>Clarity</td><td>{{ contributions.clarity }}</td></tr>
            <tr><td>Appetite</td><td>{{ contributions.appetite }}</td></tr>
            <tr><td><strong>Total</strong></td><td><strong>{{ contributions.total }}</strong></td></tr>
          </tbody>
        </table>
      </div>

      <div class="kush-card" style="margin-top:.9rem;">
        <h4 style="margin:.2rem 0 .6rem;">Product Usage Check-in</h4>
        <p class="kush-muted">Record how a specific product affected your QoL today.</p>
        <div style="display:flex; gap:.5rem; flex-wrap:wrap;">
          <a class="kw-btn secondary" href="{{ url_for('patient.products_list') }}">Browse Products</a>
          <a class="kw-btn primary" href="{{ url_for('patient.wellness_checkin') }}">Open Product Check-in</a>
        </div>
      </div>

      <div class="kush-card" style="margin-top:.9rem;">
        <h4 style="margin:.2rem 0 .6rem;">Your current products</h4>
        {% if current_products %}
          <ul class="kw-list mini" style="margin:0;">
            {% for p in current_products %}
              <li><a class="kush-link" href="{{ url_for('patient.products_list') }}?search={{ p.name|urlencode }}">{{ p.name }}</a></li>
            {% endfor %}
          </ul>
        {% else %}
          <div class="kush-muted">No products yet.</div>
        {% endif %}
      </div>

    </div>
  </section>

{% endblock %}

  // ---------- helpers ----------
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const byId = (id) => document.getElementById(id);
  const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));
  const csrf = () => {
    const m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.content : '';
  };
  const cssVar = (name, fallback) => {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name);
    return (v && v.trim()) || fallback;
  };

  // ---------- QoL scoring ----------
  function computeQoLFromForm() {
    const pain     = clamp(+byId('pain')?.value || 6, 1, 10);
    const mood     = clamp(+byId('mood')?.value || 6, 1, 10);
    const energy   = clamp(+byId('energy')?.value || 6, 1, 10);
    const clarity  = clamp(+byId('clarity')?.value || 6, 1, 10);
    const appetite = clamp(+byId('appetite')?.value || 6, 1, 10);
    const painPositive = 11 - pain; // invert (10=worst â†’ 1)
    const sum = painPositive + mood + energy + clarity + appetite; // max 50
    return clamp(Math.round(sum * 2), 0, 100); // 0â€“100%
  }

  // ---------- Center text plugin for Chart.js ----------
  const centerTextPlugin = {
    id: 'centerText',
    afterDatasetsDraw(chart, args, opts) {
      const score = chart.$centerScore;
      if (score == null) return;
      const { ctx, chartArea } = chart;
      const cx = (chartArea.left + chartArea.right) / 2;
      const cy = chartArea.top + (chartArea.bottom - chartArea.top) * (opts?.yBias ?? 0.65);
      ctx.save();
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      const fontSize = opts?.fontSize ?? 32;
      ctx.font = `800 ${fontSize}px system-ui, Segoe UI, Roboto, Helvetica, Arial, sans-serif`;
      ctx.fillStyle = cssVar('--kushwell-white', cssVar('--kw-ink', '#e9f5ee'));
      ctx.fillText(String(score), cx, cy);
      ctx.font = `700 ${Math.max(16, fontSize - 10)}px system-ui, Segoe UI, Roboto, Helvetica, Arial, sans-serif`;
      ctx.fillText('%', cx + fontSize * 0.75, cy);
      ctx.restore();
    }
  };

  // ---------- Half-donut gauge (leftâ†’right gradient) ----------
  let gauge = null, lastGradient = null;

  function makeArcGradient(ctx, area) {
    const g = ctx.createLinearGradient(area.left, 0, area.right, 0);
    g.addColorStop(0, cssVar('--kushwell-light-green', cssVar('--kw-green-500', '#10b981'))); // mint
    g.addColorStop(1, cssVar('--kushwell-dark-green', '#14532d')); // dark green
    return g;
  }

  function renderGauge(initialScore) {
    const el = byId('wellnessGauge');
    if (!el || !window.Chart) return;

    const ctx = el.getContext('2d');
    Chart.register(centerTextPlugin);

    const score = clamp(Number(initialScore ?? el.getAttribute('data-score') ?? 0), 0, 100);
    const placeholder = cssVar('--kushwell-light-green', cssVar('--kw-green-500', '#10b981'));
    const remainder = 'rgba(255,255,255,0.10)';

    gauge = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: ['Score', 'Remaining'],
        datasets: [{
          data: [score, 100 - score],
          backgroundColor: [placeholder, remainder],
          borderWidth: 0,
          hoverOffset: 0
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        rotation: Math.PI,        // start at left
        circumference: Math.PI,   // half donut
        cutout: '70%',
        plugins: {
          legend: { display: false },
          tooltip: { enabled: true },
          centerText: { fontSize: 34, yBias: 0.62 }
        }
      },
      plugins: [{
        id: 'gradientFill',
        afterLayout(chart) {
          const { ctx, chartArea } = chart;
          if (!chartArea || chartArea.width === 0) return;
          const grad = makeArcGradient(ctx, chartArea);
          chart.data.datasets[0].backgroundColor[0] = grad;
          lastGradient = grad;
        },
        beforeDatasetsDraw(chart) {
          chart.$centerScore = chart.data.datasets[0].data[0];
        }
      }]
    });
  }

  function updateGauge(score) {
    if (!gauge) return;
    const ds = gauge.data.datasets[0];
    ds.data[0] = score;
    ds.data[1] = 100 - score;
    if (lastGradient) ds.backgroundColor[0] = lastGradient;
    gauge.update();
  }

  // ---------- Quick Check-in POST ----------
  function wireCheckinSubmit() {
    const form = byId('wellness-form');
    const statusEl = byId('wellness-save-status');
    if (!form) return;

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const payload = {
        pain_level: clamp(+byId('pain').value || 0, 1, 10),
        mood_level: clamp(+byId('mood').value || 0, 1, 10),
        energy_level: clamp(+byId('energy').value || 0, 1, 10),
        clarity_level: clamp(+byId('clarity').value || 0, 1, 10),
        appetite_level: clamp(+byId('appetite').value || 0, 1, 10),
      };
      try {
        const res = await fetch(form.getAttribute('action') || form.dataset.postUrl || '/patient/wellness/checkin', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrf(),
          },
          body: JSON.stringify(payload),
        });
        if (!res.ok) {
          let msg = 'Save failed';
          try { const j = await res.json(); if (j && j.error) msg = j.error; } catch {}
          if (statusEl) statusEl.textContent = msg;
          return;
        }
        if (statusEl) statusEl.textContent = 'Saved âœ“';
        // Update gauge immediately based on current sliders
        updateGauge(computeQoLFromForm());
      } catch {
        if (statusEl) statusEl.textContent = 'Network error';
      }
    });
  }

  // ---------- Live updates from sliders ----------
  function wireSliderLiveUpdates() {
    const ids = ['pain','mood','energy','clarity','appetite'];
    const sliders = ids.map(byId).filter(Boolean);
    if (!sliders.length) return;
    const refresh = () => updateGauge(computeQoLFromForm());
    sliders.forEach(s => s.addEventListener('input', refresh));
  }

  // ---------- Card click navigation ----------
  function wireCardLinks() {
    $$('.card[data-target-url]').forEach((card) => {
      const url = card.getAttribute('data-target-url');
      if (!url) return;
      card.style.cursor = 'pointer';
      card.addEventListener('click', () => window.location.assign(url));
      card.addEventListener('keydown', (ev) => {
        if (ev.key === 'Enter' || ev.key === ' ') {
          ev.preventDefault();
          window.location.assign(url);
        }
      });
    });
  }

  // ---------- Optional: Wellness over time (line chart) ----------
  function renderLineIfPresent() {
    const el = byId('wellnessOverTime');
    if (!el || !window.Chart) return;

    let history = [];
    const json = byId('wellness-history');
    if (json) {
      try { history = JSON.parse(json.textContent || '[]'); } catch {}
    } else if (Array.isArray(window.WELLNESS_HISTORY)) {
      history = window.WELLNESS_HISTORY;
    }

    const points = history.map((h) => {
      const label = h.date || h.created_at || h.when || h.label || '';
      const value = Number(h.score ?? h.qol ?? h.value ?? h.metric ?? 0);
      return { label, value };
    }).filter(p => p.label && Number.isFinite(p.value));

    new Chart(el.getContext('2d'), {
      type: 'line',
      data: {
        labels: points.map(p => p.label),
        datasets: [{ label: 'QoL', data: points.map(p => p.value), tension: 0.25, pointRadius: 2 }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: { y: { beginAtZero: true, suggestedMax: 100 } },
        plugins: { legend: { display: false } }
      }
    });
  }

  // ---------- boot ----------
  document.addEventListener('DOMContentLoaded', () => {
    const initial = (() => {
      const el = byId('wellnessGauge');
      const attr = el?.getAttribute('data-score');
      return (attr != null) ? Number(attr) : computeQoLFromForm();
    })();
    renderGauge(initial);
    wireCheckinSubmit();
    wireSliderLiveUpdates();
    wireCardLinks();
    renderLineIfPresent();
  });
})();


