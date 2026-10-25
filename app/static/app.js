/**
 * Flock Energy — Urja Meter Ops Operations Console Frontend Client
 */

let currentPage = 1;
const pageSize = 20;
let currentChart = null;

// DOM Elements
const syncStatusBadge = document.getElementById('syncStatusBadge');
const syncStatusText = document.getElementById('syncStatusText');
const manualSyncBtn = document.getElementById('manualSyncBtn');

const kpiTotalMeters = document.getElementById('kpiTotalMeters');
const kpiInstalledMeters = document.getElementById('kpiInstalledMeters');
const kpiFaultyMeters = document.getElementById('kpiFaultyMeters');
const kpiTotalDTs = document.getElementById('kpiTotalDTs');

const searchInput = document.getElementById('searchInput');
const makeFilter = document.getElementById('makeFilter');
const statusFilter = document.getElementById('statusFilter');
const phaseFilter = document.getElementById('phaseFilter');
const resetFiltersBtn = document.getElementById('resetFiltersBtn');

const metersTableBody = document.getElementById('metersTableBody');
const prevPageBtn = document.getElementById('prevPageBtn');
const nextPageBtn = document.getElementById('nextPageBtn');
const pageIndicator = document.getElementById('pageIndicator');
const paginationInfo = document.getElementById('paginationInfo');

const transformersTableBody = document.getElementById('transformersTableBody');
const hierarchyTreeContainer = document.getElementById('hierarchyTreeContainer');

const spatialLat = document.getElementById('spatialLat');
const spatialLng = document.getElementById('spatialLng');
const spatialRadius = document.getElementById('spatialRadius');
const spatialSearchBtn = document.getElementById('spatialSearchBtn');
const spatialResultsBody = document.getElementById('spatialResultsBody');

// Modal Elements
const meterModal = document.getElementById('meterModal');
const modalCloseBtn = document.getElementById('modalCloseBtn');
const modalMeterId = document.getElementById('modalMeterId');
const modalBreadcrumbs = document.getElementById('modalBreadcrumbs');
const modalSerial = document.getElementById('modalSerial');
const modalMake = document.getElementById('modalMake');
const modalPhase = document.getElementById('modalPhase');
const modalStatus = document.getElementById('modalStatus');
const modalInstallType = document.getElementById('modalInstallType');
const modalBuild = document.getElementById('modalBuild');
const chartMetricsPills = document.getElementById('chartMetricsPills');

// Initial Load
document.addEventListener('DOMContentLoaded', () => {
  setupTabs();
  setupEventListeners();
  loadSyncStatus();
  loadMeters();
  loadTransformers();
  loadHierarchy();
});

// Tab Switcher
function setupTabs() {
  const tabs = document.querySelectorAll('.tab-btn');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));

      tab.classList.add('active');
      const targetPane = document.getElementById(tab.dataset.tab);
      if (targetPane) targetPane.classList.add('active');
    });
  });
}

// Event Listeners
function setupEventListeners() {
  let searchTimeout;
  searchInput.addEventListener('input', () => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
      currentPage = 1;
      loadMeters();
    }, 250);
  });

  makeFilter.addEventListener('change', () => { currentPage = 1; loadMeters(); });
  statusFilter.addEventListener('change', () => { currentPage = 1; loadMeters(); });
  phaseFilter.addEventListener('change', () => { currentPage = 1; loadMeters(); });

  resetFiltersBtn.addEventListener('click', () => {
    searchInput.value = '';
    makeFilter.value = '';
    statusFilter.value = '';
    phaseFilter.value = '';
    currentPage = 1;
    loadMeters();
  });

  prevPageBtn.addEventListener('click', () => {
    if (currentPage > 1) {
      currentPage--;
      loadMeters();
    }
  });

  nextPageBtn.addEventListener('click', () => {
    currentPage++;
    loadMeters();
  });

  manualSyncBtn.addEventListener('click', async () => {
    manualSyncBtn.disabled = true;
    syncStatusText.textContent = 'Syncing...';
    try {
      await fetch('/api/v1/sync', { method: 'POST' });
      await loadSyncStatus();
      await loadMeters();
      await loadTransformers();
      await loadHierarchy();
    } catch (e) {
      console.error('Manual sync failed:', e);
    } finally {
      manualSyncBtn.disabled = false;
    }
  });

  spatialSearchBtn.addEventListener('click', runSpatialSearch);

  modalCloseBtn.addEventListener('click', closeModal);
  meterModal.addEventListener('click', (e) => {
    if (e.target === meterModal) closeModal();
  });
}

// Sync Status & KPIs
async function loadSyncStatus() {
  try {
    const res = await fetch('/api/v1/sync/status');
    const data = await res.json();
    kpiTotalMeters.textContent = data.total_meters_indexed;
    kpiTotalDTs.textContent = data.total_transformers_indexed;

    syncStatusText.textContent = data.is_fresh ? 'Live & Synced' : 'Syncing...';
    const dot = syncStatusBadge.querySelector('.status-dot');
    if (data.is_fresh) {
      dot.classList.remove('syncing');
    } else {
      dot.classList.add('syncing');
    }

    // Load breakdown stats
    const statsRes = await fetch('/api/v1/meters?page_size=100');
    // Fetch installed count
    const instRes = await fetch('/api/v1/meters?install_status=Installed&page_size=1');
    const instData = await instRes.json();
    kpiInstalledMeters.textContent = instData.pagination.total_records;

    const faultRes = await fetch('/api/v1/meters?install_status=Faulty&page_size=1');
    const faultData = await faultRes.json();
    kpiFaultyMeters.textContent = faultData.pagination.total_records;
  } catch (err) {
    console.error('Failed to load sync status:', err);
  }
}

// Load Smart Meters Table
async function loadMeters() {
  metersTableBody.innerHTML = '<tr><td colspan="8" class="table-loading">Querying meters...</td></tr>';

  const params = new URLSearchParams({
    page: currentPage,
    page_size: pageSize,
  });

  if (searchInput.value.trim()) params.append('search', searchInput.value.trim());
  if (makeFilter.value) params.append('make', makeFilter.value);
  if (statusFilter.value) params.append('install_status', statusFilter.value);
  if (phaseFilter.value) params.append('phase_type', phaseFilter.value);

  try {
    const res = await fetch(`/api/v1/meters?${params.toString()}`);
    const result = await res.json();

    const meters = result.data || [];
    const pagination = result.pagination;

    pageIndicator.textContent = `Page ${pagination.page} of ${pagination.total_pages}`;
    paginationInfo.textContent = `Showing ${(pagination.page - 1) * pageSize + 1} - ${Math.min(pagination.page * pageSize, pagination.total_records)} of ${pagination.total_records} meters`;

    prevPageBtn.disabled = !pagination.has_previous;
    nextPageBtn.disabled = !pagination.has_next;

    if (meters.length === 0) {
      metersTableBody.innerHTML = '<tr><td colspan="8" class="table-loading">No matching smart meters found.</td></tr>';
      return;
    }

    metersTableBody.innerHTML = meters.map(m => {
      let statusClass = 'badge-installed';
      if (m.install_status === 'Faulty') statusClass = 'badge-faulty';
      else if (m.install_status === 'Decommissioned') statusClass = 'badge-decommissioned';

      return `
        <tr>
          <td><strong style="color: var(--accent-cyan); font-family: 'JetBrains Mono', monospace;">${m.meter_id}</strong></td>
          <td style="font-family: 'JetBrains Mono', monospace; color: var(--text-muted);">${m.serial_no}</td>
          <td><strong>${m.make}</strong></td>
          <td>${m.phase_type}</td>
          <td><span class="badge ${statusClass}">${m.install_status}</span></td>
          <td><span class="badge-code">${m.dt_code}</span></td>
          <td><span style="font-size: 0.75rem; color: var(--text-dim); text-transform: uppercase;">${m.build || 'legacy'}</span></td>
          <td>
            <button class="btn btn-outline btn-sm" onclick="inspectMeter('${m.meter_id}')">
              Inspect
            </button>
          </td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    metersTableBody.innerHTML = `<tr><td colspan="8" class="table-loading" style="color: var(--accent-rose);">Error loading meters: ${err.message}</td></tr>`;
  }
}

// Load Transformers Table
async function loadTransformers() {
  transformersTableBody.innerHTML = '<tr><td colspan="6" class="table-loading">Loading transformers...</td></tr>';
  try {
    const res = await fetch('/api/v1/transformers?page_size=50');
    const result = await res.json();
    const dts = result.data || [];

    transformersTableBody.innerHTML = dts.map(dt => `
      <tr>
        <td><span class="badge-code">${dt.code}</span></td>
        <td><strong>${dt.name}</strong></td>
        <td style="color: var(--text-muted); font-family: 'JetBrains Mono', monospace;">${dt.feeder_code}</td>
        <td>${dt.capacity_kva} kVA</td>
        <td><strong style="color: var(--accent-cyan);">${dt.meter_count}</strong> meters</td>
        <td>
          <button class="btn btn-outline btn-sm" onclick="filterByDT('${dt.code}')">
            View Meters
          </button>
        </td>
      </tr>
    `).join('');
  } catch (err) {
    transformersTableBody.innerHTML = `<tr><td colspan="6" class="table-loading" style="color: var(--accent-rose);">Error loading transformers: ${err.message}</td></tr>`;
  }
}

function filterByDT(dtCode) {
  document.querySelector('[data-tab="tabMeters"]').click();
  searchInput.value = '';
  makeFilter.value = '';
  statusFilter.value = '';
  phaseFilter.value = '';
  // Set DT filter search
  searchInput.value = dtCode;
  currentPage = 1;
  loadMeters();
}

// Load Network Hierarchy Tree
async function loadHierarchy() {
  hierarchyTreeContainer.innerHTML = '<div class="table-loading">Building distribution tree...</div>';
  try {
    const res = await fetch('/api/v1/network/hierarchy');
    const tree = await res.json();

    let html = '';
    const zones = tree.zones || {};
    for (const [zCode, zone] of Object.entries(zones)) {
      html += `<div class="tree-node">
        <span class="tree-node-title">⚡ ${zone.name} (${zone.code})</span>`;

      for (const [cCode, circle] of Object.entries(zone.circles || {})) {
        html += `<div class="tree-node">
          <span class="tree-node-title">🏢 ${circle.name} (${circle.code})</span>`;

        for (const [dCode, div] of Object.entries(circle.divisions || {})) {
          html += `<div class="tree-node">
            <span class="tree-node-title">📂 ${div.name} (${div.code})</span>`;

          for (const [sdCode, subdiv] of Object.entries(div.subdivisions || {})) {
            html += `<div class="tree-node">
              <span class="tree-node-title">📁 ${subdiv.name} (${subdiv.code})</span>`;

            for (const [ssCode, ss] of Object.entries(subdiv.substations || {})) {
              html += `<div class="tree-node">
                <span class="tree-node-title">🏭 ${ss.name} (${ss.code})</span>`;

              for (const [fCode, feeder] of Object.entries(ss.feeders || {})) {
                html += `<div class="tree-node">
                  <span class="tree-node-title">🔌 Feeder: ${feeder.name} (${feeder.code})</span>`;

                for (const [dtCode, dt] of Object.entries(feeder.transformers || {})) {
                  html += `<div class="tree-node">
                    <span class="tree-node-title">🔋 ${dt.name} (${dt.code})</span>
                    <span class="tree-node-meta"> — ${dt.meters_count} smart meters connected</span>
                  </div>`;
                }
                html += `</div>`;
              }
              html += `</div>`;
            }
            html += `</div>`;
          }
          html += `</div>`;
        }
        html += `</div>`;
      }
      html += `</div>`;
    }

    hierarchyTreeContainer.innerHTML = html;
  } catch (err) {
    hierarchyTreeContainer.innerHTML = `<div class="table-loading" style="color: var(--accent-rose);">Error building hierarchy: ${err.message}</div>`;
  }
}

// Proximity / Spatial Search
async function runSpatialSearch() {
  spatialResultsBody.innerHTML = '<tr><td colspan="6" class="table-loading">Computing distances...</td></tr>';
  const lat = parseFloat(spatialLat.value);
  const lng = parseFloat(spatialLng.value);
  const radius = parseFloat(spatialRadius.value);

  try {
    const res = await fetch(`/api/v1/meters/nearby?lat=${lat}&lng=${lng}&radius_km=${radius}&limit=25`);
    const results = await res.json();

    if (results.length === 0) {
      spatialResultsBody.innerHTML = '<tr><td colspan="6" class="table-loading">No smart meters found within specified radius.</td></tr>';
      return;
    }

    spatialResultsBody.innerHTML = results.map(item => `
      <tr>
        <td><strong style="color: var(--accent-emerald);">${item.distance_km} km</strong></td>
        <td><strong style="color: var(--accent-cyan); font-family: 'JetBrains Mono', monospace;">${item.meter_id}</strong></td>
        <td>${item.make}</td>
        <td><span class="badge badge-installed">${item.install_status}</span></td>
        <td><span class="badge-code">${item.dt_code}</span></td>
        <td style="font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; color: var(--text-dim);">
          ${item.location ? `${item.location.lat.toFixed(4)}, ${item.location.lng.toFixed(4)}` : '—'}
        </td>
      </tr>
    `).join('');
  } catch (err) {
    spatialResultsBody.innerHTML = `<tr><td colspan="6" class="table-loading" style="color: var(--accent-rose);">Error: ${err.message}</td></tr>`;
  }
}

// Inspect Meter Modal Drawer & Chart
async function inspectMeter(meterId) {
  modalMeterId.textContent = `Meter ${meterId}`;
  modalBreadcrumbs.textContent = 'Loading hierarchy & profile...';
  chartMetricsPills.innerHTML = '';
  meterModal.classList.add('open');

  try {
    // 1. Fetch meter details
    const [detailRes, readingsRes] = await Promise.all([
      fetch(`/api/v1/meters/${meterId}`),
      fetch(`/api/v1/meters/${meterId}/readings?order=asc`)
    ]);

    const detail = await detailRes.json();
    const readingsData = await readingsRes.json();

    // Populate specs
    modalSerial.textContent = detail.serial_no || '—';
    modalMake.textContent = detail.make || '—';
    modalPhase.textContent = detail.phase_type || '—';
    modalStatus.textContent = detail.install_status || '—';
    modalInstallType.textContent = detail.install_type || 'Whole Current';
    modalBuild.textContent = (detail.build || 'legacy').toUpperCase();

    if (detail.hierarchy) {
      const h = detail.hierarchy;
      modalBreadcrumbs.textContent = `${h.zone.name} › ${h.circle.name} › ${h.division.name} › ${h.substation.name} › ${h.feeder.name} › ${h.dt.name}`;
    }

    // Populate metrics pills
    const m = readingsData.metrics;
    if (m) {
      chartMetricsPills.innerHTML = `
        <span class="metric-pill">Consumed: <strong>${m.total_delta_kwh} kWh</strong></span>
        <span class="metric-pill">Avg Voltage: <strong>${m.avg_voltage_v} V</strong></span>
        <span class="metric-pill">Power Factor: <strong>${m.avg_power_factor || '0.92'}</strong></span>
        <span class="metric-pill">Peak Interval: <strong>${m.peak_interval_kwh} kWh</strong></span>
      `;
    }

    // Plot Chart.js
    plotConsumptionChart(readingsData.readings || []);

  } catch (err) {
    console.error('Failed to load meter details:', err);
    modalBreadcrumbs.textContent = 'Error loading details.';
  }
}

function plotConsumptionChart(readings) {
  const canvas = document.getElementById('consumptionChart');
  if (currentChart) {
    currentChart.destroy();
  }

  // Sample or thin readings if 337 points are too crowded
  const step = Math.max(1, Math.floor(readings.length / 48)); // roughly 48 points
  const sampled = readings.filter((_, idx) => idx % step === 0);

  const labels = sampled.map(r => r.timestamp);
  const deltaValues = sampled.map(r => r.delta_kwh || 0.0);
  const voltages = sampled.map(r => r.voltage_r || 230);

  currentChart = new Chart(canvas, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Interval Delta (kWh)',
          data: deltaValues,
          borderColor: '#06b6d4',
          backgroundColor: 'rgba(6, 182, 212, 0.1)',
          fill: true,
          tension: 0.3,
          yAxisID: 'yConsumption',
        },
        {
          label: 'R-Phase Voltage (V)',
          data: voltages,
          borderColor: '#f59e0b',
          borderDash: [4, 4],
          pointRadius: 0,
          tension: 0.2,
          yAxisID: 'yVoltage',
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: 'index',
        intersect: false,
      },
      scales: {
        x: {
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
          ticks: { color: '#9ca3af', font: { size: 10 }, maxTicksLimit: 8 }
        },
        yConsumption: {
          type: 'linear',
          position: 'left',
          title: { display: true, text: 'Interval kWh', color: '#06b6d4' },
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
          ticks: { color: '#9ca3af' }
        },
        yVoltage: {
          type: 'linear',
          position: 'right',
          title: { display: true, text: 'Voltage (V)', color: '#f59e0b' },
          grid: { drawOnChartArea: false },
          ticks: { color: '#9ca3af' },
          min: 210,
          max: 250
        }
      },
      plugins: {
        legend: { labels: { color: '#f3f4f6' } }
      }
    }
  });
}

function closeModal() {
  meterModal.classList.remove('open');
  if (currentChart) {
    currentChart.destroy();
    currentChart = null;
  }
}
