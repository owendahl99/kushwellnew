// FILE: static/js/enterprise_dashboard.js
// Purpose: traffic chart (line), safe across pages.

(function () {
  const onReady = (fn) =>
    (document.readyState === "loading")
      ? document.addEventListener("DOMContentLoaded", fn, { once: true })
      : fn();

  onReady(() => {
    const el = document.getElementById("trafficChart");
    if (!el || !window.Chart) return; // not on this page or Chart.js not loaded

    // Expect these to be rendered by Jinja; fall back safely if not.
    let labels = [];
    let values = [];
    try {
      // If embedded via data-* (preferred), use those:
      if (el.dataset.labels && el.dataset.values) {
        labels = JSON.parse(el.dataset.labels);
        values = JSON.parse(el.dataset.values);
      } else {
        // Or (legacy) global variables injected by the template:
        labels = window.__traffic_labels__ || [];
        values = window.__traffic_values__ || [];
      }
    } catch {
      labels = []; values = [];
    }

    if (!Array.isArray(labels) || !Array.isArray(values) || labels.length === 0) return;

    new Chart(el, {
      type: "line",
      data: {
        labels,
        datasets: [{
          label: "Unique Views",
          data: values,
          borderColor: "#2563eb",
          backgroundColor: "rgba(37, 99, 235, 0.2)",
          tension: 0.4,
          fill: true
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: { beginAtZero: true, ticks: { stepSize: 10 } },
          x: { grid: { display: false } }
        },
        plugins: { legend: { display: true } }
      }
    });
  });
})();


