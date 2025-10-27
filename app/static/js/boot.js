// Harden fetch with CSRF, add tiny DOM helpers, and fail-safe theme checks.
(function () {
  // --- Helpers ---
  window.$  = (sel, root = document) => root.querySelector(sel);
  window.$$ = (sel, root = document) => Array.prototype.slice.call(root.querySelectorAll(sel));
  window.ready = (fn) => {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', fn, { once: true });
    } else {
      try { fn(); } catch {}
    }
  };
  window.on = (el, evt, fn, opts) => { if (el) el.addEventListener(evt, fn, opts); };

  // --- CSRF patch for fetch ---
  const meta = document.querySelector('meta[name="csrf-token"]');
  const CSRF = meta ? meta.content : null;
  const _fetch = window.fetch;
  window.fetch = function (input, init = {}) {
    const method = (init.method || 'GET').toUpperCase();
    if (CSRF && !['GET','HEAD','OPTIONS'].includes(method)) {
      init.headers = Object.assign({ 'X-CSRFToken': CSRF }, init.headers || {});
      if (!('credentials' in init)) init.credentials = 'include';
    }
    return _fetch(input, init);
  };

  // --- Theme force-on (diagnostic + auto-fix) ---
  ready(() => {
    // 1) Ensure <body class="kw-body">
    const body = document.body;
    if (body && !body.classList.contains('kw-body')) {
      body.classList.add('kw-body');
    }

    // 2) Check if kushwell.css is active by inspecting computed background.
    const bg = body ? getComputedStyle(body).backgroundColor : '';
    const looksWhite = !bg || /rgba?\(\s*255\s*,\s*255\s*,\s*255/i.test(bg) || bg === 'transparent';

    // 3) If it still looks white/transparent, inject emergency theme styles.
    if (looksWhite) {
      const style = document.createElement('style');
      style.setAttribute('data-kushwell-emergency', '1');
      style.textContent = `
        :root{
          --kushwell-green:#2f4f4f;
          --kushwell-light-green:#10b981;
          --kushwell-dark-green:#14532d;
          --kushwell-white:#e0e6d6;
          --kushwell-yellow:#f5d547;
        }
        html, body { background: var(--kushwell-dark-green) !important; color: var(--kushwell-white) !important; }
        .kw-nav { background: var(--kushwell-green) !important; border-bottom: 3px solid var(--kushwell-light-green) !important; }
        .card { background: var(--kushwell-green) !important; border:2px solid var(--kushwell-light-green) !important; border-radius:14px; padding:1rem; box-shadow:0 6px 12px rgba(0,0,0,.5); }
        .btn-primary{ background:var(--kushwell-light-green) !important; color:var(--kushwell-green) !important; font-weight:800; border:none; border-radius:10px; padding:.65rem 1rem; cursor:pointer; }
        .btn-primary:hover{ background:var(--kushwell-yellow) !important; color:var(--kushwell-dark-green) !important; }
        .kw-link{ color:var(--kushwell-white) !important; text-decoration:none; }
        .kw-link:hover{ color:var(--kushwell-yellow) !important; text-decoration:underline; }
      `;
      document.head.appendChild(style);
      console.warn('[Kushwell] Emergency theme styles injected: base CSS not detected.');
    }
  });
})();


