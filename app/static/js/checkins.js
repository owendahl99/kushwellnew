document.addEventListener("DOMContentLoaded", function() {
  // === Wellness Slider ===
  const slider = document.getElementById("wellnessSlider");
  const sliderValue = document.getElementById("sliderValue");
  slider.addEventListener("input", () => {
    sliderValue.textContent = slider.value;
  });

  document.getElementById("submitWellness").addEventListener("click", () => {
    const value = slider.value;
    fetch("/patient/submit_wellness_feedback", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCSRFToken()  // Flask-WTF if using CSRF
      },
      body: JSON.stringify({ wellness_score: value })
    })
    .then(response => response.json())
    .then(data => {
      alert("Wellness submitted!");
      updateGauges(data.gauges);
      updateChart(data.analytics);
    })
    .catch(err => console.error(err));
  });

  // === Wellness Gauges (simple rendering) ===
  function updateGauges(gauges) {
    document.querySelectorAll(".gauge").forEach((gauge, idx) => {
      gauge.textContent = `${gauges[idx].label}: ${gauges[idx].value}%`;
      gauge.style.width = `${gauges[idx].value}%`;
      gauge.style.backgroundColor = "#4caf50";
      gauge.style.height = "20px";
      gauge.style.margin = "5px 0";
    });
  }

  // === Wellness Comparative Chart ===
  const ctx = document.getElementById("wellnessChart").getContext("2d");
  let wellnessChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: [], // Dates or periods
      datasets: [
        {
          label: 'Wellness Score',
          data: [],
          borderColor: 'rgba(75, 192, 192, 1)',
          fill: false
        }
      ]
    },
    options: {
      responsive: true,
      scales: {
        y: { beginAtZero: true, max: 100 }
      }
    }
  });

  function updateChart(data) {
    wellnessChart.data.labels = data.labels;
    wellnessChart.data.datasets[0].data = data.scores;
    wellnessChart.update();
  }

  // === Check-in Buttons ===
  document.getElementById("newCheckin").addEventListener("click", () => {
    window.location.href = "/patient/new_checkin";
  });

  document.getElementById("viewHistory").addEventListener("click", () => {
    window.location.href = "/patient/checkin_history";
  });

  // === Helper: CSRF Token ===
  function getCSRFToken() {
    const cookie = document.cookie.split(";").find(c => c.trim().startsWith("csrf_token="));
    return cookie ? cookie.split("=")[1] : "";
  }
});


