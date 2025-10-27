// FILE: static/js/wellness.js
(function () {
  var form = document.getElementById("wellness-form");
  if (!form) return;

  var action = form.getAttribute("data-json-action") || form.getAttribute("action");
  if (!action) return;

  // helper to get input value
  function _get(name) {
    var el = form.querySelector('[name="' + name + '"]');
    return el ? (el.value || "").trim() : "";
  }

  // helper to get integer value from *_level or fallback
  function _intPref(base) {
    var v = _get(base + "_level");
    if (v === "") v = _get(base);
    var n = parseInt(v, 10);
    return isNaN(n) ? null : Math.max(1, Math.min(10, n));
  }

  form.addEventListener("submit", function (ev) {
    ev.preventDefault();

    var next = form.querySelector('input[name="next"]')?.value || "";

    var payload = {
      pain_level: _intPref("pain"),
      mood_level: _intPref("mood"),
      energy_level: _intPref("energy"),
      clarity_level: _intPref("clarity"),
      appetite_level: _intPref("appetite"),
      notes: _get("notes") || _get("notes_global") || null,
      afflictions: Array.from(form.querySelectorAll('input[name="afflictions[]"]')).map(i => i.value),
      next: next
    };

    fetch(action, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      credentials: "same-origin"
    })
      .then(r => r.json().catch(() => ({ ok: false })))
      .then(j => {
        if (j && j.ok) {
          window.location.href = next || "/patient/dashboard";
        } else {
          // fallback to normal form post if JSON path fails
          form.submit();
        }
      })
      .catch(function () { form.submit(); });
  });
})();


