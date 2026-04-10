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

function baseOptions(c, xLabel, yLabel, extra) {
  var opts = {
    responsive: true,
    maintainAspectRatio: true,
    aspectRatio: 1.8,
    layout: { padding: { top: 10, right: 16, bottom: 4, left: 4 } },
    plugins: {
      legend: {
        position: "bottom",
        labels: {
          color: c.text,
          usePointStyle: true,
          pointStyle: "line",
          padding: 16,
          font: { size: 12 },
        },
      },
    },
    scales: {
      x: {
        type: "linear",
        title: { display: true, text: xLabel, color: c.text, padding: { top: 8 }, font: { size: 12 } },
        ticks: { color: c.text, font: { size: 11 }, maxTicksLimit: 8 },
        grid:  { color: c.grid },
      },
      y: {
        title: { display: true, text: yLabel, color: c.text, padding: { bottom: 8 }, font: { size: 12 } },
        ticks: { color: c.text, font: { size: 11 }, maxTicksLimit: 7 },
        grid:  { color: c.grid },
      },
    },
  };

  // Merge extra scale options
  if (extra && extra.y) {
    for (var k in extra.y) { opts.scales.y[k] = extra.y[k]; }
  }
  if (extra && extra.x) {
    for (var k2 in extra.x) { opts.scales.x[k2] = extra.x[k2]; }
  }
  if (extra && extra.aspectRatio) {
    opts.aspectRatio = extra.aspectRatio;
  }
  return opts;
}

/* ------------------------------------------------------------------ */
/*  STDP                                                               */
/* ------------------------------------------------------------------ */

function renderSTDP(canvas) {
  var c = getColors();
  var tau = 7, aPlus = 1.0, aMinus = 0.8;

  var ltp = [], ltd = [];
  for (var dt = -7; dt <= 0; dt += 0.2) {
    ltp.push({ x: dt, y: aPlus * Math.exp(-Math.abs(dt) / tau) });
  }
  for (var dt2 = 0; dt2 <= 7; dt2 += 0.2) {
    ltd.push({ x: dt2, y: -aMinus * Math.exp(-Math.abs(dt2) / tau) });
  }

  new Chart(canvas, {
    type: "scatter",
    data: {
      datasets: [
        { label: "LTP (strengthen)", data: ltp, showLine: true, borderColor: c.ltp, borderWidth: 2.5, pointRadius: 0, fill: false },
        { label: "LTD (weaken)", data: ltd, showLine: true, borderColor: c.ltd, borderWidth: 2.5, pointRadius: 0, fill: false },
      ],
    },
    options: baseOptions(c, "\u0394t (days)", "\u0394w", {
      aspectRatio: 1.5,
      y: { min: -1.2, max: 1.2, ticks: { stepSize: 0.4 } },
      x: { min: -8, max: 8 },
    }),
  });
}

/* ------------------------------------------------------------------ */
/*  LIF                                                                */
/* ------------------------------------------------------------------ */

function renderLIF(canvas) {
  var c = getColors();
  var tauM = 6, fires = [5, 14, 23], threshVal = 0.65;

  var pts = [], pressure = 0.1;
  for (var t = 0; t <= 32; t += 0.3) {
    for (var f = 0; f < fires.length; f++) {
      if (Math.abs(t - fires[f]) < 0.3) {
        pressure += 0.55;  // deterministic jump
      }
    }
    pts.push({ x: t, y: pressure });
    pressure *= Math.exp(-0.3 / tauM);
  }

  var thLine = [{ x: 0, y: threshVal }, { x: 32, y: threshVal }];

  new Chart(canvas, {
    type: "scatter",
    data: {
      datasets: [
        { label: "pressure", data: pts, showLine: true, borderColor: c.pressure, borderWidth: 2.5, pointRadius: 0, fill: false },
        { label: "threshold", data: thLine, showLine: true, borderColor: c.threshold, borderWidth: 1.5, borderDash: [6, 4], pointRadius: 0, fill: false },
      ],
    },
    options: baseOptions(c, "time", "pressure", {
      y: { min: 0, max: 1.0, ticks: { stepSize: 0.2 } },
      x: { min: 0, max: 34 },
    }),
  });
}

/* ------------------------------------------------------------------ */
/*  Forgetting Curve                                                   */
/* ------------------------------------------------------------------ */

function renderForgettingCurve(canvas) {
  var c = getColors();

  var noReview = [];
  var stability0 = 8;
  for (var t = 0; t <= 60; t += 0.5) {
    noReview.push({ x: t, y: 100 * Math.exp(-t / stability0) });
  }

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

  var markers = reviews.map(function (r) { return { x: r, y: 100 }; });

  new Chart(canvas, {
    type: "scatter",
    data: {
      datasets: [
        { label: "with spaced review", data: spaced, showLine: true, borderColor: c.review, borderWidth: 2.5, pointRadius: 0, fill: false },
        { label: "without review", data: noReview, showLine: true, borderColor: c.decay, borderWidth: 2, borderDash: [6, 4], pointRadius: 0, fill: false },
        { label: "review point", data: markers, showLine: false, borderColor: c.fire, backgroundColor: c.fire, pointRadius: 5, pointStyle: "triangle" },
      ],
    },
    options: baseOptions(c, "time (days)", "recall %", {
      y: { min: 0, max: 110, ticks: { stepSize: 20 } },
      x: { min: 0, max: 65 },
    }),
  });
}
