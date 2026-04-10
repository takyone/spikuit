/**
 * Spikuit concept diagrams — Chart.js renderers.
 *
 * Each <canvas data-chart="name"> is auto-rendered on page load.
 * Re-renders on MkDocs Material theme toggle (light/dark).
 */

/* ------------------------------------------------------------------ */
/*  Palette                                                            */
/* ------------------------------------------------------------------ */

function getColors() {
  var dark =
    document.body.getAttribute("data-md-color-scheme") === "slate";
  return {
    text:      dark ? "#ccc" : "#555",
    grid:      dark ? "#444" : "#e0e0e0",
    ltp:       "#4CAF50",
    ltd:       "#E53935",
    pressure:  "#7C4DFF",
    threshold: "#FF9800",
    decay:     dark ? "#888" : "#BDBDBD",
    review:    "#2196F3",
    fire:      "#4CAF50",
    bg:        dark ? "#1e1e1e" : "#ffffff",
  };
}

/* ------------------------------------------------------------------ */
/*  Bootstrap                                                          */
/* ------------------------------------------------------------------ */

function initCharts() {
  if (typeof Chart === "undefined") {
    return setTimeout(initCharts, 100);
  }

  document.querySelectorAll("canvas[data-chart]").forEach(function (el) {
    var existing = Chart.getChart(el);
    if (existing) existing.destroy();

    var fn = { stdp: renderSTDP, lif: renderLIF, "forgetting-curve": renderForgettingCurve }[
      el.dataset.chart
    ];
    if (fn) fn(el);
  });
}

document.addEventListener("DOMContentLoaded", initCharts);

// MkDocs Material instant-navigation support
if (typeof document$ !== "undefined") {
  document$.subscribe(function () { initCharts(); });
}

// Re-render on theme toggle
new MutationObserver(initCharts).observe(document.body, {
  attributes: true,
  attributeFilter: ["data-md-color-scheme"],
});

/* ------------------------------------------------------------------ */
/*  Shared helpers                                                     */
/* ------------------------------------------------------------------ */

function baseScales(c, xLabel, yLabel) {
  return {
    x: {
      type: "linear",
      title: { display: true, text: xLabel, color: c.text },
      ticks: { color: c.text },
      grid:  { color: c.grid },
    },
    y: {
      title: { display: true, text: yLabel, color: c.text },
      ticks: { color: c.text },
      grid:  { color: c.grid },
    },
  };
}

function baseLegend(c) {
  return { labels: { color: c.text, usePointStyle: true, pointStyle: "line" } };
}

/* ------------------------------------------------------------------ */
/*  STDP                                                               */
/* ------------------------------------------------------------------ */

function renderSTDP(canvas) {
  var c = getColors();
  var tau = 7, aPlus = 1.0, aMinus = 0.8;

  // LTP: dt < 0 (pre before post)
  var ltp = [], ltd = [];
  for (var dt = -7; dt <= 0; dt += 0.2) {
    ltp.push({ x: dt, y: aPlus * Math.exp(-Math.abs(dt) / tau) });
  }
  // LTD: dt > 0 (post before pre)
  for (var dt2 = 0; dt2 <= 7; dt2 += 0.2) {
    ltd.push({ x: dt2, y: -aMinus * Math.exp(-Math.abs(dt2) / tau) });
  }

  new Chart(canvas, {
    type: "scatter",
    data: {
      datasets: [
        { label: "LTP (+)", data: ltp, showLine: true, borderColor: c.ltp, borderWidth: 2.5, pointRadius: 0, fill: false },
        { label: "LTD (\u2212)", data: ltd, showLine: true, borderColor: c.ltd, borderWidth: 2.5, pointRadius: 0, fill: false },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      aspectRatio: 1.6,
      plugins: { legend: baseLegend(c) },
      scales: Object.assign(baseScales(c, "\u0394t (days)", "\u0394w"), {
        y: {
          title: { display: true, text: "\u0394w", color: c.text },
          ticks: { color: c.text },
          grid:  { color: c.grid },
          min: -1.1, max: 1.1,
        },
      }),
    },
  });
}

/* ------------------------------------------------------------------ */
/*  LIF                                                                */
/* ------------------------------------------------------------------ */

function renderLIF(canvas) {
  var c = getColors();
  var tauM = 6, fires = [5, 14, 23], threshVal = 0.65;

  // Build piecewise pressure curve
  var pts = [], pressure = 0.1;
  for (var t = 0; t <= 32; t += 0.3) {
    // check for fire events
    for (var f = 0; f < fires.length; f++) {
      if (Math.abs(t - fires[f]) < 0.3) {
        pressure += 0.5 + Math.random() * 0.2;
      }
    }
    pts.push({ x: t, y: pressure });
    pressure *= Math.exp(-0.3 / tauM);
  }

  // Threshold flat line
  var thLine = [{ x: 0, y: threshVal }, { x: 32, y: threshVal }];

  new Chart(canvas, {
    type: "scatter",
    data: {
      datasets: [
        { label: "pressure", data: pts, showLine: true, borderColor: c.pressure, borderWidth: 2.5, pointRadius: 0, fill: false },
        { label: "threshold", data: thLine, showLine: true, borderColor: c.threshold, borderWidth: 1.5, borderDash: [6, 4], pointRadius: 0, fill: false },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      aspectRatio: 1.8,
      plugins: { legend: baseLegend(c) },
      scales: Object.assign(baseScales(c, "time", "pressure"), {
        y: {
          title: { display: true, text: "pressure", color: c.text },
          ticks: { color: c.text },
          grid:  { color: c.grid },
          min: 0,
        },
      }),
    },
  });
}

/* ------------------------------------------------------------------ */
/*  Forgetting Curve                                                   */
/* ------------------------------------------------------------------ */

function renderForgettingCurve(canvas) {
  var c = getColors();

  // Without review: pure exponential decay
  var noReview = [];
  var stability0 = 8;
  for (var t = 0; t <= 60; t += 0.5) {
    noReview.push({ x: t, y: 100 * Math.exp(-t / stability0) });
  }

  // With spaced review: stability grows after each review
  var reviews = [12, 28, 50];
  var stabilities = [8, 16, 32, 60];
  var spaced = [], recall = 100, stab = stabilities[0], lastReview = 0, ri = 0;

  for (var t2 = 0; t2 <= 60; t2 += 0.5) {
    if (ri < reviews.length && t2 >= reviews[ri]) {
      recall = 100;
      lastReview = reviews[ri];
      ri++;
      stab = stabilities[ri];
    }
    spaced.push({ x: t2, y: recall * Math.exp(-(t2 - lastReview) / stab) });
  }

  // Review point markers
  var markers = reviews.map(function (r) { return { x: r, y: 100 }; });

  new Chart(canvas, {
    type: "scatter",
    data: {
      datasets: [
        { label: "with spaced review", data: spaced, showLine: true, borderColor: c.review, borderWidth: 2.5, pointRadius: 0, fill: false },
        { label: "without review", data: noReview, showLine: true, borderColor: c.decay, borderWidth: 2, borderDash: [6, 4], pointRadius: 0, fill: false },
        { label: "review", data: markers, showLine: false, borderColor: c.fire, backgroundColor: c.fire, pointRadius: 6, pointStyle: "triangle" },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      aspectRatio: 1.8,
      plugins: { legend: baseLegend(c) },
      scales: Object.assign(baseScales(c, "time (days)", "recall %"), {
        y: {
          title: { display: true, text: "recall %", color: c.text },
          ticks: { color: c.text },
          grid:  { color: c.grid },
          min: 0, max: 105,
        },
      }),
    },
  });
}
