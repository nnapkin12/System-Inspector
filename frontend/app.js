/* Scan-first UI with utilization graphs. Desktop shell optional. */

const $ = (id) => document.getElementById(id);

const PRIMARY_FIELDS = {
  os: ["pretty_name", "kernel", "architecture", "desktop_environment", "hostname", "uptime_seconds"],
  system: ["vendor", "product", "version"],
  motherboard: ["vendor", "product", "version"],
  bios: ["vendor", "version", "date"],
  chassis: ["vendor", "type"],
  cpu: ["brand", "cores_physical", "cores_logical", "freq_max_mhz", "cache_l3"],
  gpu: ["vendor", "driver_version", "vram_total_mb", "pci_id"],
  memory: ["total_gb", "module_count"],
  swap: ["total_gb"],
  disk: ["model", "media", "size_gb", "device"],
  partition: ["mountpoint", "fstype", "total_gb", "percent"],
  network: ["is_up", "speed_mbps"],
  network_controller: [],
  battery: ["percent", "power_plugged"],
  pci_group: ["count"],
};

const CATEGORY_META = {
  os: { label: "Operating system", icon: "os" },
  system: { label: "Machine", icon: "system" },
  motherboard: { label: "Motherboard", icon: "board" },
  bios: { label: "Firmware", icon: "bios" },
  chassis: { label: "Chassis", icon: "chassis" },
  cpu: { label: "Processor", icon: "cpu" },
  gpu: { label: "Graphics", icon: "gpu" },
  memory: { label: "Memory", icon: "ram" },
  swap: { label: "Swap", icon: "ram" },
  disk: { label: "Storage", icon: "disk" },
  partition: { label: "Volume", icon: "disk" },
  network: { label: "Network", icon: "net" },
  network_controller: { label: "Network chip", icon: "net" },
  battery: { label: "Battery", icon: "bat" },
  pci_group: { label: "PCI bus", icon: "pci" },
};

const SORT_ORDER = [
  "gpu",
  "cpu",
  "motherboard",
  "memory",
  "disk",
  "system",
  "bios",
  "battery",
  "os",
  "partition",
  "swap",
  "network",
  "network_controller",
  "chassis",
  "pci_group",
];

const ICONS = {
  cpu: `<svg viewBox="0 0 24 24"><rect x="7" y="7" width="10" height="10" rx="1"/><path d="M9 3v4M12 3v4M15 3v4M9 17v4M12 17v4M15 17v4M3 9h4M3 12h4M3 15h4M17 9h4M17 12h4M17 15h4"/></svg>`,
  gpu: `<svg viewBox="0 0 24 24"><rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="9" cy="12" r="2.5"/><path d="M14 10h5M14 12h4M14 14h5"/></svg>`,
  ram: `<svg viewBox="0 0 24 24"><rect x="2" y="7" width="20" height="10" rx="1"/><path d="M6 17v2M10 17v2M14 17v2M18 17v2M6 7V5M10 7V5M14 7V5M18 7V5"/></svg>`,
  disk: `<svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="12" cy="12" r="3"/><path d="M7 8h.01"/></svg>`,
  net: `<svg viewBox="0 0 24 24"><path d="M5 12h14"/><path d="M12 5v14"/><circle cx="12" cy="12" r="3"/><path d="M5 5l2 2M19 5l-2 2M5 19l2-2M19 19l-2-2"/></svg>`,
  os: `<svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="14" rx="2"/><path d="M8 21h8M12 18v3"/></svg>`,
  system: `<svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="12" rx="2"/><path d="M8 21h8M12 17v4"/></svg>`,
  board: `<svg viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="2"/><rect x="7" y="7" width="4" height="4"/><rect x="13" y="7" width="4" height="3"/><path d="M7 15h10M7 18h6"/></svg>`,
  bios: `<svg viewBox="0 0 24 24"><path d="M12 3l8 4v6c0 4.5-3.2 7.5-8 9-4.8-1.5-8-4.5-8-9V7l8-4z"/></svg>`,
  chassis: `<svg viewBox="0 0 24 24"><rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 7h6M9 11h6M9 15h4"/></svg>`,
  bat: `<svg viewBox="0 0 24 24"><rect x="2" y="7" width="18" height="10" rx="2"/><path d="M20 10h2v4h-2"/><rect x="4" y="9" width="10" height="6"/></svg>`,
  pci: `<svg viewBox="0 0 24 24"><path d="M4 8h16v8H4z"/><path d="M7 16v3M11 16v3M15 16v3M19 16v3"/></svg>`,
};

const HISTORY_MAX = 120;
const history = {
  cpu: [],
  gpu: [],
  ram: [],
  cpuTemp: [],
  gpuTemp: [],
  diskRead: [],
  diskWrite: [],
  netRecv: [],
  netSent: [],
};

/** Client-side IO baseline so speeds work even if backend rates are missing. */
let prevCounters = null;

let monitorWs = null;
let pollTimer = null;
let monitoring = false;
let openVital = null;
let lastVitals = null;
let lastScan = null;

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function fmtPct(n) {
  if (n == null || Number.isNaN(n)) return "—";
  return `${Math.round(n)}%`;
}

function fmtTemp(n) {
  if (n == null || Number.isNaN(n)) return "—";
  return `${Math.round(n)}°`;
}

function fmtRate(n) {
  if (n == null || Number.isNaN(n)) return "—";
  const v = Number(n);
  if (v < 0.01) return "0 MB/s";
  if (v < 0.1) return `${v.toFixed(2)} MB/s`;
  if (v < 10) return `${v.toFixed(1)} MB/s`;
  return `${Math.round(v)} MB/s`;
}

function fmtUptime(sec) {
  if (sec == null || Number.isNaN(sec)) return null;
  const s = Math.floor(sec);
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function numOrNull(n) {
  return n == null || Number.isNaN(Number(n)) ? null : Number(n);
}

function setBar(el, pct) {
  if (!el) return;
  const v = Math.max(0, Math.min(100, Number(pct) || 0));
  el.style.width = `${v}%`;
  el.classList.remove("warn", "danger");
  if (v >= 90) el.classList.add("danger");
  else if (v >= 75) el.classList.add("warn");
}

function setStatus(text, tone = "muted") {
  const el = $("status-pill");
  if (!el) return;
  el.textContent = text;
  el.className = "pill";
  if (tone === "ok") el.classList.add("pill-ok");
  else if (tone === "bad") el.classList.add("pill-bad");
  else if (tone === "busy") el.classList.add("pill-busy");
  else el.classList.add("pill-muted");
}

function prettyKey(key) {
  return key.replaceAll("_", " ");
}

function formatField(key, value) {
  if (value == null) return "—";
  if (key === "uptime_seconds") return fmtUptime(value) || String(value);
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (typeof value === "object") return null;
  return String(value);
}

function pushHistory(series, value) {
  const v = numOrNull(value);
  if (v == null) return;
  series.push({ t: Date.now(), v });
  if (series.length > HISTORY_MAX) series.shift();
}

function clearHistory() {
  for (const k of Object.keys(history)) history[k] = [];
}

function switchTab(name) {
  const scan = name === "scan";
  $("tab-scan").classList.toggle("is-active", scan);
  $("tab-util").classList.toggle("is-active", !scan);
  $("tab-scan").setAttribute("aria-selected", scan ? "true" : "false");
  $("tab-util").setAttribute("aria-selected", scan ? "false" : "true");
  $("panel-scan").hidden = !scan;
  $("panel-util").hidden = scan;
}

function groupComponents(components) {
  const pci = [];
  const items = [];
  for (const c of components || []) {
    if (c.category === "pci") pci.push(c);
    else items.push(c);
  }
  if (pci.length) {
    items.push({ category: "pci_group", name: "PCI devices", count: pci.length, devices: pci });
  }
  items.sort((a, b) => {
    const ia = SORT_ORDER.indexOf(a.category);
    const ib = SORT_ORDER.indexOf(b.category);
    return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
  });
  return items;
}

function buildPrimaryEntries(item) {
  const keys = PRIMARY_FIELDS[item.category] || [];
  const entries = [];
  for (const key of keys) {
    if (item[key] == null || typeof item[key] === "object") continue;
    entries.push({ key, value: formatField(key, item[key]) });
  }
  if (!entries.length) {
    for (const [key, value] of Object.entries(item)) {
      if (["category", "name", "devices"].includes(key)) continue;
      const s = formatField(key, value);
      if (s == null) continue;
      entries.push({ key, value: s });
      if (entries.length >= 5) break;
    }
  }
  return entries;
}

function buildExtra(item) {
  const primary = new Set(PRIMARY_FIELDS[item.category] || []);
  const extra = {};
  for (const [key, value] of Object.entries(item)) {
    if (["category", "name", "devices"].includes(key) || value == null) continue;
    if (!primary.has(key) || typeof value === "object") extra[key] = value;
  }
  return extra;
}

function renderCard(item) {
  const meta = CATEGORY_META[item.category] || { label: item.category || "Device", icon: "system" };
  const icon = ICONS[meta.icon] || ICONS.system;
  const card = document.createElement("article");
  card.className = "hw-card";

  const face = document.createElement("button");
  face.type = "button";
  face.className = "hw-card-face";
  face.innerHTML = `
    <div class="hw-icon" aria-hidden="true">${icon}</div>
    <div class="hw-text">
      <div class="hw-type">${escapeHtml(meta.label)}</div>
      <div class="hw-title">${escapeHtml(item.name || "Unknown")}</div>
    </div>
    <div class="hw-spacer"></div>
    <span class="hw-chevron" aria-hidden="true">›</span>
  `;

  const body = document.createElement("div");
  body.className = "hw-body";

  const primary = buildPrimaryEntries(item);
  if (primary.length) {
    const ul = document.createElement("ul");
    ul.className = "detail-list";
    for (const { key, value } of primary) {
      const li = document.createElement("li");
      li.innerHTML = `<span class="k">${escapeHtml(prettyKey(key))}</span><span class="v">${escapeHtml(value)}</span>`;
      ul.appendChild(li);
    }
    body.appendChild(ul);
  }

  if (item.category === "pci_group" && item.devices) {
    const box = document.createElement("div");
    box.className = "pci-lines";
    for (const d of item.devices) {
      const line = document.createElement("div");
      line.className = "pci-line";
      line.textContent = d.name || d.raw || "device";
      box.appendChild(line);
    }
    body.appendChild(box);
  }

  const extra = buildExtra(item);
  if (Object.keys(extra).length) {
    const more = document.createElement("details");
    more.className = "more-meta";
    more.innerHTML = `<summary>Technical details</summary>`;
    const pre = document.createElement("div");
    pre.className = "more-meta-body";
    pre.textContent = JSON.stringify(extra, null, 2);
    more.appendChild(pre);
    body.appendChild(more);
  }

  face.addEventListener("click", () => {
    const open = card.classList.toggle("is-open");
    face.setAttribute("aria-expanded", open ? "true" : "false");
  });

  card.appendChild(face);
  card.appendChild(body);
  return card;
}

function showScanEmpty(msg) {
  $("scan-empty").classList.remove("is-hidden");
  $("scan-results").classList.add("is-hidden");
  $("btn-export").disabled = true;
  if (msg) $("scan-status").textContent = msg;
}

function showScanResults(data) {
  lastScan = data;
  $("scan-empty").classList.add("is-hidden");
  $("scan-results").classList.remove("is-hidden");
  $("btn-export").disabled = false;

  const s = data.summary || {};
  const bits = [s.hostname, s.os, s.desktop, fmtUptime(s.uptime_seconds) ? `up ${fmtUptime(s.uptime_seconds)}` : null].filter(
    Boolean
  );
  $("scan-summary").textContent = bits.join("  ·  ");
  $("scan-status").textContent = `Last scan ${new Date(data.collected_at || Date.now()).toLocaleString()}`;
  const grid = $("hw-grid");
  grid.innerHTML = "";
  for (const item of groupComponents(data.components)) {
    grid.appendChild(renderCard(item));
  }
}

function exportScan() {
  if (!lastScan) return;
  const blob = new Blob([JSON.stringify(lastScan, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  const host = (lastScan.summary && lastScan.summary.hostname) || "machine";
  a.href = URL.createObjectURL(blob);
  a.download = `system-inspector-${host}-${Date.now()}.json`;
  a.click();
  URL.revokeObjectURL(a.href);
}

async function runScan() {
  const btn = $("btn-scan");
  btn.disabled = true;
  btn.textContent = "Scanning…";
  setStatus("scanning", "busy");
  $("scan-status").textContent = "Reading hardware…";
  try {
    const includePci = $("toggle-pci").checked;
    const res = await fetch(`/api/inventory?include_pci=${includePci ? "true" : "false"}`);
    if (!res.ok) throw new Error(`Scan failed (${res.status})`);
    showScanResults(await res.json());
    setStatus("scanned", "ok");
  } catch (err) {
    showScanEmpty(String(err.message || err));
    setStatus("error", "bad");
  } finally {
    btn.disabled = false;
    btn.textContent = "Scan system";
  }
}

function extractMetrics(data, { recordCounters = true } = {}) {
  const cpu = data.cpu || {};
  const gpus = data.gpus || [];
  const gpu = gpus[0] || {};
  const ram = (data.memory && data.memory.ram) || {};
  const rates = data.rates || {};
  const counters = data.counters || {};
  const cpuTemp = (cpu.temperatures && cpu.temperatures[0] && cpu.temperatures[0].celsius) ?? null;
  const gpuTemp = gpu.temperature_c ?? null;

  // Prefer client-side rates from absolute counters (works across server reloads)
  let diskRead = null;
  let diskWrite = null;
  let netRecv = null;
  let netSent = null;

  const now = performance.now() / 1000;
  const hasCounters =
    counters.disk_read_bytes != null ||
    counters.net_recv_bytes != null ||
    (data.storage && data.storage.io && data.storage.io.read_bytes != null) ||
    (data.network && data.network.total && data.network.total.bytes_recv != null);

  if (hasCounters) {
    const cur = {
      t: now,
      diskRead: Number(
        counters.disk_read_bytes ?? (data.storage && data.storage.io && data.storage.io.read_bytes) ?? 0
      ),
      diskWrite: Number(
        counters.disk_write_bytes ?? (data.storage && data.storage.io && data.storage.io.write_bytes) ?? 0
      ),
      netRecv: Number(
        counters.net_recv_bytes ?? (data.network && data.network.total && data.network.total.bytes_recv) ?? 0
      ),
      netSent: Number(
        counters.net_sent_bytes ?? (data.network && data.network.total && data.network.total.bytes_sent) ?? 0
      ),
    };
    if (prevCounters && cur.t > prevCounters.t) {
      const dt = Math.max(cur.t - prevCounters.t, 0.05);
      const mbs = (a, b) => Math.max(a - b, 0) / dt / (1024 * 1024);
      diskRead = mbs(cur.diskRead, prevCounters.diskRead);
      diskWrite = mbs(cur.diskWrite, prevCounters.diskWrite);
      netRecv = mbs(cur.netRecv, prevCounters.netRecv);
      netSent = mbs(cur.netSent, prevCounters.netSent);
    }
    if (recordCounters) {
      prevCounters = cur;
    }
  }

  // Fall back to backend-computed rates after first server interval
  if (diskRead == null && rates.ready) {
    diskRead = numOrNull(rates.disk_read_mbs) ?? 0;
    diskWrite = numOrNull(rates.disk_write_mbs) ?? 0;
    netRecv = numOrNull(rates.net_recv_mbs) ?? 0;
    netSent = numOrNull(rates.net_sent_mbs) ?? 0;
  }

  const diskTotal =
    diskRead != null || diskWrite != null ? (diskRead || 0) + (diskWrite || 0) : null;
  const netTotal = netRecv != null || netSent != null ? (netRecv || 0) + (netSent || 0) : null;

  return {
    cpuPct: numOrNull(cpu.usage_percent),
    gpuPct: numOrNull(gpu.usage_percent),
    ramPct: numOrNull(ram.percent),
    cpuTemp: numOrNull(cpuTemp),
    gpuTemp: numOrNull(gpuTemp),
    diskRead,
    diskWrite,
    diskTotal,
    netRecv,
    netSent,
    netTotal,
    cpu,
    gpu,
    gpus,
    ram,
    rates,
    fans: data.fans || [],
    fansAvailable: data.fans_available,
    battery: data.battery || null,
    partitions: (data.storage && data.storage.partitions) || [],
  };
}

function recordHistory(m) {
  pushHistory(history.cpu, m.cpuPct);
  pushHistory(history.gpu, m.gpuPct);
  pushHistory(history.ram, m.ramPct);
  pushHistory(history.cpuTemp, m.cpuTemp);
  pushHistory(history.gpuTemp, m.gpuTemp);
  pushHistory(history.diskRead, m.diskRead);
  pushHistory(history.diskWrite, m.diskWrite);
  pushHistory(history.netRecv, m.netRecv);
  pushHistory(history.netSent, m.netSent);
}

function renderSideband(m) {
  const el = $("sideband");
  const chips = [];

  if (m.battery) {
    const plug = m.battery.power_plugged ? "plugged" : "on battery";
    chips.push({ k: "Battery", v: `${Math.round(m.battery.percent)}% · ${plug}` });
  }

  const realFans = (m.fans || []).filter((f) => {
    if (f.percent != null && f.percent > 0) return true;
    if (f.rpm != null && f.rpm > 0) return true;
    return false;
  });
  if (realFans.length) {
    realFans
      .sort((a, b) => (b.rpm || b.percent || 0) - (a.rpm || a.percent || 0))
      .slice(0, 4)
      .forEach((f) => {
        const val =
          f.rpm != null && f.rpm > 0
            ? `${Math.round(f.rpm)} RPM`
            : f.percent != null
              ? `${Math.round(f.percent)}%`
              : "—";
        chips.push({ k: f.label || f.sensor || "Fan", v: val });
      });
  }

  const root = m.partitions.find((p) => p.mountpoint === "/") || m.partitions[0];
  if (root && root.percent != null) {
    chips.push({
      k: `Disk ${root.mountpoint || ""}`.trim(),
      v: `${root.percent}% · ${root.used_gb ?? "—"} / ${root.total_gb ?? "—"} GB`,
    });
  }

  if (!chips.length) {
    el.classList.add("is-hidden");
    el.innerHTML = "";
    return;
  }
  el.classList.remove("is-hidden");
  el.innerHTML = chips
    .map(
      (c) =>
        `<div class="side-chip"><div class="k">${escapeHtml(c.k)}</div><div class="v">${escapeHtml(c.v)}</div></div>`
    )
    .join("");
}

function renderVitals(data) {
  if (!data) return;
  lastVitals = data;
  const m = extractMetrics(data, { recordCounters: true });
  recordHistory(m);

  const cpu = m.cpu;
  const gpu = m.gpu;
  const ram = m.ram;

  $("cpu-usage").textContent = fmtPct(m.cpuPct);
  setBar($("cpu-bar"), m.cpuPct);
  const freq = cpu.freq_current_mhz != null ? `${Math.round(cpu.freq_current_mhz)} MHz` : null;
  const cores = cpu.usage_per_core ? `${cpu.usage_per_core.length} threads` : null;
  $("cpu-detail").textContent =
    [freq, cores, m.cpuTemp != null ? `Temp ${fmtTemp(m.cpuTemp)}C` : null].filter(Boolean).join("  ·  ") ||
    "—";

  $("gpu-usage").textContent = fmtPct(m.gpuPct);
  setBar($("gpu-bar"), m.gpuPct);
  $("gpu-detail").textContent = [
    gpu.name || null,
    m.gpu.vram_used_mb != null && m.gpu.vram_total_mb != null
      ? `${Math.round(m.gpu.vram_used_mb)} / ${Math.round(m.gpu.vram_total_mb)} MB`
      : null,
    m.gpu.power_watts != null ? `${m.gpu.power_watts} W` : null,
  ]
    .filter(Boolean)
    .join("  ·  ") || "No GPU metrics";

  $("ram-usage").textContent = fmtPct(m.ramPct);
  setBar($("ram-bar"), m.ramPct);
  $("ram-detail").textContent =
    ram.used_gb != null && ram.total_gb != null ? `${ram.used_gb} / ${ram.total_gb} GB in use` : "—";

  $("temp-cpu").textContent = m.cpuTemp != null ? `${fmtTemp(m.cpuTemp)}C` : "—";
  $("temp-gpu").textContent = m.gpuTemp != null ? `${fmtTemp(m.gpuTemp)}C` : "—";
  $("temp-detail").textContent = [
    m.cpuTemp != null ? "CPU sensor live" : "CPU sensor n/a",
    m.gpuTemp != null ? "GPU sensor live" : "GPU sensor n/a",
  ].join("  ·  ");

  $("disk-usage").textContent = m.diskTotal != null ? fmtRate(m.diskTotal) : "…";
  $("disk-detail").textContent =
    m.diskRead != null || m.diskWrite != null
      ? `Read ${fmtRate(m.diskRead ?? 0)}  ·  Write ${fmtRate(m.diskWrite ?? 0)}`
      : "Measuring… (need ~1s)";

  $("net-usage").textContent = m.netTotal != null ? fmtRate(m.netTotal) : "…";
  $("net-detail").textContent =
    m.netRecv != null || m.netSent != null
      ? `↓ ${fmtRate(m.netRecv ?? 0)}  ·  ↑ ${fmtRate(m.netSent ?? 0)}`
      : "Measuring… (need ~1s)";

  renderSideband(m);

  $("util-status").textContent = `Live · ${new Date(data.collected_at || Date.now()).toLocaleTimeString()}`;

  if (openVital) refreshModal(openVital);
}

function drawSeries(canvas, seriesList, opts = {}) {
  const dpr = window.devicePixelRatio || 1;
  const cssW = canvas.clientWidth || 640;
  const cssH = canvas.clientHeight || 200;
  canvas.width = Math.floor(cssW * dpr);
  canvas.height = Math.floor(cssH * dpr);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const w = cssW;
  const h = cssH;
  ctx.clearRect(0, 0, w, h);

  ctx.strokeStyle = "rgba(255,255,255,0.06)";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = (h / 4) * i;
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(w, y);
    ctx.stroke();
  }

  const all = seriesList.flatMap((s) => s.data.map((p) => p.v));
  if (!all.length) {
    ctx.fillStyle = "rgba(176,154,162,0.85)";
    ctx.font = "14px system-ui,sans-serif";
    ctx.fillText("No samples yet — keep monitoring open", 12, h / 2);
    return;
  }

  let min = opts.min != null ? opts.min : Math.min(...all);
  let max = opts.max != null ? opts.max : Math.max(...all);
  if (min === max) {
    min -= 1;
    max += 1;
  }
  const pad = (max - min) * 0.08 || 1;
  min -= pad;
  max += pad;

  const colors = opts.colors || ["#d64545", "#e08870"];

  seriesList.forEach((series, si) => {
    const data = series.data;
    if (data.length < 1) return;
    ctx.strokeStyle = colors[si % colors.length];
    ctx.lineWidth = 2;
    ctx.beginPath();
    data.forEach((p, i) => {
      const x = data.length === 1 ? w / 2 : (i / (data.length - 1)) * (w - 8) + 4;
      const y = h - 8 - ((p.v - min) / (max - min)) * (h - 16);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    const last = data[data.length - 1];
    const x = data.length === 1 ? w / 2 : w - 4;
    const y = h - 8 - ((last.v - min) / (max - min)) * (h - 16);
    ctx.fillStyle = colors[si % colors.length];
    ctx.beginPath();
    ctx.arc(x, y, 3.5, 0, Math.PI * 2);
    ctx.fill();
  });
}

function modalConfig(key) {
  const m = lastVitals ? extractMetrics(lastVitals, { recordCounters: false }) : null;
  switch (key) {
    case "cpu":
      return {
        title: "CPU load",
        sub: "Usage over time while monitoring is running",
        value: m ? fmtPct(m.cpuPct) : "—",
        unit: "",
        series: [{ name: "CPU %", data: history.cpu }],
        yMin: 0,
        yMax: 100,
        colors: ["#d64545"],
        stats: m
          ? [
              { k: "Load", v: fmtPct(m.cpuPct) },
              { k: "Frequency", v: m.cpu.freq_current_mhz != null ? `${Math.round(m.cpu.freq_current_mhz)} MHz` : "—" },
              { k: "Load avg 1m", v: m.cpu.load_1m != null ? String(m.cpu.load_1m) : "—" },
              { k: "Temp", v: m.cpuTemp != null ? `${fmtTemp(m.cpuTemp)}C` : "—" },
              { k: "Threads", v: m.cpu.usage_per_core ? String(m.cpu.usage_per_core.length) : "—" },
            ]
          : [],
      };
    case "gpu":
      return {
        title: "GPU load",
        sub: m?.gpu?.name || "Graphics utilization",
        value: m ? fmtPct(m.gpuPct) : "—",
        unit: "",
        series: [{ name: "GPU %", data: history.gpu }],
        yMin: 0,
        yMax: 100,
        colors: ["#e07058"],
        stats: m
          ? [
              { k: "Load", v: fmtPct(m.gpuPct) },
              {
                k: "VRAM",
                v:
                  m.gpu.vram_used_mb != null
                    ? `${Math.round(m.gpu.vram_used_mb)} / ${Math.round(m.gpu.vram_total_mb)} MB`
                    : "—",
              },
              { k: "Power", v: m.gpu.power_watts != null ? `${m.gpu.power_watts} W` : "—" },
              { k: "Temp", v: m.gpuTemp != null ? `${fmtTemp(m.gpuTemp)}C` : "—" },
              {
                k: "Clocks",
                v:
                  m.gpu.graphics_mhz != null
                    ? `${m.gpu.graphics_mhz} / ${m.gpu.mem_mhz || "—"} MHz`
                    : "—",
              },
            ]
          : [],
      };
    case "ram":
      return {
        title: "Memory",
        sub: "RAM utilization",
        value: m ? fmtPct(m.ramPct) : "—",
        unit: "",
        series: [{ name: "RAM %", data: history.ram }],
        yMin: 0,
        yMax: 100,
        colors: ["#c48a4a"],
        stats: m
          ? [
              { k: "Used", v: m.ram.used_gb != null ? `${m.ram.used_gb} GB` : "—" },
              { k: "Total", v: m.ram.total_gb != null ? `${m.ram.total_gb} GB` : "—" },
              { k: "Available", v: m.ram.available_gb != null ? `${m.ram.available_gb} GB` : "—" },
              { k: "Percent", v: fmtPct(m.ramPct) },
            ]
          : [],
      };
    case "temps":
      return {
        title: "Temperatures",
        sub: "CPU and GPU · both lines on one graph",
        value:
          m && (m.cpuTemp != null || m.gpuTemp != null)
            ? `${m.cpuTemp != null ? fmtTemp(m.cpuTemp) + "C" : "—"}  /  ${m.gpuTemp != null ? fmtTemp(m.gpuTemp) + "C" : "—"}`
            : "—",
        unit: "CPU / GPU",
        series: [
          { name: "CPU", data: history.cpuTemp },
          { name: "GPU", data: history.gpuTemp },
        ],
        colors: ["#d64545", "#e8a090"],
        stats: m
          ? [
              { k: "CPU now", v: m.cpuTemp != null ? `${fmtTemp(m.cpuTemp)}C` : "—" },
              { k: "GPU now", v: m.gpuTemp != null ? `${fmtTemp(m.gpuTemp)}C` : "—" },
              {
                k: "CPU peak (session)",
                v: history.cpuTemp.length
                  ? `${fmtTemp(Math.max(...history.cpuTemp.map((p) => p.v)))}C`
                  : "—",
              },
              {
                k: "GPU peak (session)",
                v: history.gpuTemp.length
                  ? `${fmtTemp(Math.max(...history.gpuTemp.map((p) => p.v)))}C`
                  : "—",
              },
            ]
          : [],
      };
    case "disk":
      return {
        title: "Disk I/O",
        sub: "Read and write throughput",
        value: m ? fmtRate(m.diskTotal) : "—",
        unit: "total",
        series: [
          { name: "Read", data: history.diskRead },
          { name: "Write", data: history.diskWrite },
        ],
        colors: ["#d64545", "#e8a090"],
        stats: m
          ? [
              { k: "Read", v: fmtRate(m.diskRead) },
              { k: "Write", v: fmtRate(m.diskWrite) },
              { k: "Total", v: fmtRate(m.diskTotal) },
            ]
          : [],
      };
    case "net":
      return {
        title: "Network",
        sub: "Download and upload throughput",
        value: m ? fmtRate(m.netTotal) : "—",
        unit: "total",
        series: [
          { name: "Recv", data: history.netRecv },
          { name: "Sent", data: history.netSent },
        ],
        colors: ["#d64545", "#c48a4a"],
        stats: m
          ? [
              { k: "Download", v: fmtRate(m.netRecv) },
              { k: "Upload", v: fmtRate(m.netSent) },
              { k: "Total", v: fmtRate(m.netTotal) },
            ]
          : [],
      };
    default:
      return null;
  }
}

function refreshModal(key) {
  const cfg = modalConfig(key);
  if (!cfg) return;
  $("modal-title").textContent = cfg.title;
  $("modal-sub").textContent = cfg.sub;
  $("modal-value").textContent = cfg.value;
  $("modal-unit").textContent = cfg.unit || "";
  $("modal-stats").innerHTML = cfg.stats
    .map((s) => `<div class="modal-stat"><div class="k">${escapeHtml(s.k)}</div><div class="v">${escapeHtml(s.v)}</div></div>`)
    .join("");

  const n = Math.max(...cfg.series.map((s) => s.data.length), 0);
  $("chart-caption").textContent =
    n > 0
      ? `${n} sample${n === 1 ? "" : "s"} · last ~${Math.min(n, HISTORY_MAX)}s while monitoring`
      : "History fills while Start monitoring is active";

  drawSeries($("modal-chart"), cfg.series, {
    min: cfg.yMin,
    max: cfg.yMax,
    colors: cfg.colors,
  });
}

function openModal(key) {
  openVital = key;
  $("modal").classList.remove("is-hidden");
  document.body.classList.add("modal-open");
  refreshModal(key);
}

function closeModal() {
  openVital = null;
  $("modal").classList.add("is-hidden");
  document.body.classList.remove("modal-open");
}

function showUtilIdle() {
  $("util-idle").classList.remove("is-hidden");
  $("util-live").classList.add("is-hidden");
}

function showUtilLive() {
  $("util-idle").classList.add("is-hidden");
  $("util-live").classList.remove("is-hidden");
}

function stopMonitoring() {
  monitoring = false;
  closeModal();
  if (monitorWs) {
    try {
      monitorWs.close();
    } catch {
      /* */
    }
    monitorWs = null;
  }
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  clearHistory();
  lastVitals = null;
  prevCounters = null;
  showUtilIdle();
  $("btn-monitor").textContent = "Start monitoring";
  $("btn-monitor").classList.remove("btn-danger");
  $("btn-monitor").classList.add("btn-primary");
  $("util-status").textContent = "Monitoring stopped. Graph history cleared.";
  setStatus("idle", "muted");
}

function startPolling() {
  if (pollTimer) return;
  const tick = async () => {
    if (!monitoring) return;
    try {
      const res = await fetch("/api/vitals");
      if (!res.ok) throw new Error("vitals");
      renderVitals(await res.json());
      setStatus("live", "ok");
    } catch {
      setStatus("error", "bad");
    }
  };
  tick();
  pollTimer = setInterval(tick, 1000);
}

function startMonitoring() {
  if (monitoring) {
    stopMonitoring();
    return;
  }
  monitoring = true;
  clearHistory();
  prevCounters = null;
  showUtilLive();
  $("btn-monitor").textContent = "Stop monitoring";
  $("btn-monitor").classList.remove("btn-primary");
  $("btn-monitor").classList.add("btn-danger");
  $("util-status").textContent = "Connecting…";
  setStatus("live", "busy");

  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/vitals`);
  monitorWs = ws;

  ws.addEventListener("open", () => setStatus("live", "ok"));
  ws.addEventListener("message", (ev) => {
    if (!monitoring) return;
    try {
      renderVitals(JSON.parse(ev.data));
    } catch {
      /* */
    }
  });
  ws.addEventListener("close", () => {
    if (!monitoring) return;
    monitorWs = null;
    startPolling();
  });
  ws.addEventListener("error", () => {
    try {
      ws.close();
    } catch {
      /* */
    }
  });
}

$("tab-scan").addEventListener("click", () => switchTab("scan"));
$("tab-util").addEventListener("click", () => switchTab("util"));
$("btn-scan").addEventListener("click", () => runScan());
$("btn-export").addEventListener("click", () => exportScan());
$("btn-monitor").addEventListener("click", () => startMonitoring());

document.querySelectorAll(".util-tile").forEach((tile) => {
  tile.addEventListener("click", () => {
    if (!monitoring) return;
    openModal(tile.dataset.vital);
  });
});

$("modal-close").addEventListener("click", () => closeModal());
$("modal-backdrop").addEventListener("click", () => closeModal());
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeModal();
  if (e.key === "s" && !e.metaKey && !e.ctrlKey && e.target.tagName !== "INPUT") {
    if (!$("panel-scan").hidden) runScan();
  }
});

setStatus("idle", "muted");
showScanEmpty("Nothing loaded yet. Run a scan to inventory this machine.");
showUtilIdle();
