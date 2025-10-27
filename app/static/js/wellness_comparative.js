// FILE: static/js/wellness_comparative.js

document.addEventListener("DOMContentLoaded", () => {
  // Slider inputs
  const sliders = document.querySelectorAll(".wc-slider");
  const comparativeCard = document.getElementById("wellnessComparativeCard");
  const overallScoreEl = document.getElementById("wcOverallScore");
  const comparativeList = document.getElementById("wcComparativeList");
  const encouragementEl = document.getElementById("wcEncouragement");

  // Last check-in values (provided by Flask as JSON)
  const lastCheckin = window.lastCheckin || {}; // e.g., { sleep: 5, energy: 6 }
  
  // Product allocation (optional)
  const productUsage = window.productUsage || []; // [{ product_id, name, allocation }]
  
  // Helper: calculate percentage change
  const pctChange = (current, previous) => {
    if (previous === null || previous === undefined || previous === 0) return null;
    return ((current - previous) / previous) * 100;
  };

  // Generate encouragement text
  const generateEncouragement = (comparisons) => {
    const improvements = [], deteriorations = [], stable = [];
    comparisons.forEach(s => {
      if (s.pct_change === null || isNaN(s.pct_change)) return;
      if (s.pct_change > 2) improvements.push(s.category);
      else if (s.pct_change < -2) deteriorations.push(s.category);
      else stable.push(s.category);
    });

    if (improvements.length && !deteriorations.length)
      return `Great job! Your scores for ${improvements.join(", ")} have improved since your last check-in. Keep up the good work!`;
    if (deteriorations.length && !improvements.length)
      return `We noticed a decrease in ${deteriorations.join(", ")} since your last check-in. Small setbacks are part of the journey.`;
    if (improvements.length && deteriorations.length)
      return `You've improved in ${improvements.join(", ")}, but ${deteriorations.join(", ")} have declined. Let's keep working together.`;
    if (stable.length)
      return `Your scores remain stable in ${stable.join(", ")}. Maintaining consistency is great!`;
    return "No significant changes detected this time. Keep monitoring your progress.";
  };

  // Update the Wellness Comparative card dynamically
  const updateComparative = () => {
    const comparisons = [];
    let totalCurrent = 0, totalPrevious = 0, count = 0;

    sliders.forEach(slider => {
      const category = slider.dataset.category;
      const current = parseFloat(slider.value);
      const previous = lastCheckin[category] ?? null;
      const pct = pctChange(current, previous);
      comparisons.push({ category, current, previous, pct_change: pct });

      if (!isNaN(current)) { totalCurrent += current; count++; }
      if (!isNaN(previous)) totalPrevious += previous;
    });

    // Overall score
    const overallPct = pctChange(totalCurrent / count, totalPrevious / count);
    overallScoreEl.textContent = `Overall Score: ${Math.round(totalCurrent / count)} (${overallPct !== null ? overallPct.toFixed(1) + "% change" : "N/A"})`;

    // Slider-by-slider changes
    comparativeList.innerHTML = comparisons.map(c => {
      const pctText = c.pct_change !== null ? `${c.pct_change.toFixed(1)}%` : "N/A";
      return `<li><strong>${c.category}</strong>: ${c.current} (Last: ${c.previous ?? "â€”"}), Change: ${pctText}</li>`;
    }).join("");

    // Encouragement
    encouragementEl.textContent = generateEncouragement(comparisons);
  };

  // Event listeners for sliders
  sliders.forEach(slider => slider.addEventListener("input", updateComparative));

  // Initial render
  updateComparative();
});


