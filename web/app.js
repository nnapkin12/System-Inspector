/* Local system monitor. Talks only to /api on this same host. */
(() => {
  "use strict";

  const INTERVAL_MS = 1000;
  const HISTORY = 90;

  const PAGES = {
    overview: { title: "Overview", hint: "same vitals as si status", tokens: ["status"], live: true },
    cpu: { title: "CPU", hint: "si cpu", tokens: ["cpu"], live: true },
    gpu: { title: "GPU", hint: "si gpu", tokens: ["gpu"], live: true },
    memory: { title: "Memory", hint: "si ram", tokens: ["ram"], live: true },
    storage: { title: "Storage", hint: "si disk", tokens: ["disk"], live: true },
    network: { title: "Network", hint: "si net", tokens: ["net"], live: true },
    sensors: { title: "Sensors", hint: "temps, fans, battery", tokens: ["temps", "fans", "battery"], live: true },
    // Not bundled with "version": `os version` is the distro field, not the app.
    system: { title: "System", hint: "os, board, displays", tokens: ["os", "board", "display", "uptime"], live: false },
  };

  const main = document.getElementById("main");
  const hosttext = document.getElementById("hosttext");
  const tagline = document.getElementById("tagline");
  const pulse = document.getElementById("pulse");
  const navLinks = [...document.querySelectorAll(".side a[data-page]")];

  const history = {
    cpu: [],
    ram: [],
    gpu: [],
    netIn: [],
    netOut: [],
    diskR: [],
    diskW: [],
  };

  let page = "overview";
  let timer = null;
  let identity = null;
  let lastError = null;
  let extra = { netSlice: null, scan: null, busy: false };

  function push(key, value) {
    const n = Number(value);
    const series = history[key];
    if (!series) return;
    series.push(Number.isFinite(n) ? n : null);
    if (series.length > HISTORY) series.shift();
  }

  function dash(v) {
    if (v === null || v === undefined || v === "") return "—";
    return String(v);
  }

  function pct(v) {
    if (v === null || v === undefined || Number.isNaN(Number(v))) return "—";
    return `${Math.round(Number(v))}%`;
  }

  function deg(v) {
    if (v === null || v === undefined || Number.isNaN(Number(v))) return "—";
    return `${Math.round(Number(v))}°C`;
  }

  function num(v, digits) {
    if (v === null || v === undefined || Number.isNaN(Number(v))) return "—";
    const n = Number(v);
    if (digits === 0) return String(Math.round(n));
    if (Math.abs(n) >= 10) return n.toFixed(1);
    return n.toFixed(digits ?? 1);
  }

  function fmtHz(v) {
    if (v === null || v === undefined || Number.isNaN(Number(v))) return "—";
    const x = Number(v);
    if (Math.abs(x - Math.round(x)) < 0.05) return `${Math.round(x)} Hz`;
    return `${x} Hz`;
  }

  function fmtUptime(secs) {
    if (secs === null || secs === undefined || Number.isNaN(Number(secs))) return "—";
    let s = Math.max(0, Math.floor(Number(secs)));
    const days = Math.floor(s / 86400);
    s %= 86400;
    const hours = Math.floor(s / 3600);
    s %= 3600;
    const mins = Math.floor(s / 60);
    const parts = [];
    if (days) parts.push(`${days} day${days === 1 ? "" : "s"}`);
    if (hours || days) parts.push(`${hours} hour${hours === 1 ? "" : "s"}`);
    parts.push(`${mins} min${mins === 1 ? "" : "s"}`);
    return parts.join(", ");
  }

  function heat(pctVal) {
    const n = Number(pctVal);
    if (!Number.isFinite(n)) return "";
    if (n >= 90) return "bad";
    if (n >= 75) return "warn";
    return "";
  }

  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (v === null || v === undefined || v === false) continue;
        if (k === "class") node.className = v;
        else if (k === "text") node.textContent = v;
        else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
        else node.setAttribute(k, v === true ? "" : String(v));
      }
    }
    for (const child of children) {
      if (child === null || child === undefined || child === false) continue;
      node.append(child.nodeType ? child : document.createTextNode(String(child)));
    }
    return node;
  }

  function bar(value, kind) {
    const n = Number(value);
    const width = Number.isFinite(n) ? Math.max(0, Math.min(100, n)) : 0;
    let warn = "";
    if (kind === "temp") {
      if (n >= 85) warn = "bad";
      else if (n >= 70) warn = "warn";
    } else if (kind === "cpu" || kind === "ram" || kind === "gpu" || kind === "disk") {
      warn = heat(n);
    }
    const wrap = el("div", { class: `bar ${kind || ""} ${warn}`.trim() });
    const fill = el("i");
    fill.style.width = `${width}%`;
    wrap.append(fill);
    return wrap;
  }

  function sparkline(series, color) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "spark");
    svg.setAttribute("viewBox", "0 0 90 36");
    svg.setAttribute("preserveAspectRatio", "none");
    svg.setAttribute("aria-hidden", "true");
    const pts = (series || []).filter((v) => v !== null && v !== undefined && Number.isFinite(Number(v)));
    if (pts.length < 2) return svg;
    const max = Math.max(1, ...pts.map(Number));
    const w = 90;
    const h = 36;
    const step = w / Math.max(1, (series.length - 1));
    const coords = [];
    series.forEach((v, i) => {
      const n = Number(v);
      if (!Number.isFinite(n)) return;
      const x = (i * step).toFixed(2);
      const y = (h - (n / max) * (h - 4) - 2).toFixed(2);
      coords.push(`${x},${y}`);
    });
    if (coords.length < 2) return svg;
    const line = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
    line.setAttribute("points", coords.join(" "));
    line.setAttribute("stroke", color || "#88c0d0");
    svg.append(line);
    return svg;
  }

  function props(rows) {
    const dl = el("dl", { class: "props" });
    for (const [k, v] of rows) {
      if (v === null || v === undefined || v === "") continue;
      dl.append(el("dt", { text: k }), el("dd", { text: dash(v) }));
    }
    return dl;
  }

  function pageHead(info) {
    return el(
      "div",
      { class: "page-head" },
      el("h2", { text: info.title }),
      el("p", { class: "hint", text: info.hint }),
    );
  }

  function note(text) {
    return el("p", { class: "note", text });
  }

  function section(payload, resource) {
    if (!payload) return {};
    if (payload.resource === "bundle") {
      return (payload.results || []).find((r) => r.resource === resource) || {};
    }
    return payload;
  }

  function dataOf(payload, resource) {
    const block = resource ? section(payload, resource) : payload;
    if (!block.ok && block.error) return null;
    return block.data || {};
  }

  async function query(tokens) {
    const q = tokens.join(" ");
    const res = await fetch(`/api/query?${new URLSearchParams({ q })}`);
    const body = await res.json();
    if (!res.ok && !body.ok) {
      throw new Error(body.error || `HTTP ${res.status}`);
    }
    return body;
  }

  function setLive(ok, stale) {
    pulse.classList.toggle("off", !ok);
    pulse.classList.toggle("stale", Boolean(ok && stale));
  }

  function rememberStatus(payload) {
    const d = dataOf(payload, "status");
    if (!d) return;
    identity = d;
    const live = d.live || {};
    push("cpu", live.cpu_percent);
    push("ram", live.ram_percent);
    push("gpu", live.gpu_percent);
    if (live.rates_ready) {
      push("netIn", live.net_recv_mbs);
      push("netOut", live.net_sent_mbs);
      push("diskR", live.disk_read_mbs);
      push("diskW", live.disk_write_mbs);
    }
    hosttext.textContent = [d.hostname, d.os, fmtUptime(d.uptime_seconds)].filter(Boolean).join("  ·  ");
  }

  function metricCard(title, valueEl, barEl, extraEl, sparkEl) {
    const card = el("article", { class: "card metric" }, el("h3", { text: title }));
    const row = el("div", { class: "row" });
    row.append(valueEl);
    if (extraEl) row.append(extraEl);
    card.append(row);
    if (barEl) card.append(barEl);
    if (sparkEl) card.append(sparkEl);
    return card;
  }

  function renderOverview(payload) {
    const d = dataOf(payload, "status");
    if (!d) return fail(payload);
    const live = d.live || {};
    const rates = live.rates_ready;
    const frag = document.createDocumentFragment();
    frag.append(pageHead(PAGES.overview));
    frag.append(
      el(
        "p",
        { class: "ident" },
        [d.cpu, (d.gpus || [])[0], d.ram_gb != null ? `${d.ram_gb} GB RAM` : null]
          .filter(Boolean)
          .join("  ·  ") || "—",
      ),
    );
    const grid = el("div", { class: "grid" });
    grid.append(
      metricCard(
        "CPU",
        el("div", { class: "value" }, pct(live.cpu_percent)),
        bar(live.cpu_percent, "cpu"),
        el("span", { class: "detail", text: deg(live.cpu_temp_c) }),
        sparkline(history.cpu, "#88c0d0"),
      ),
      metricCard(
        "Memory",
        el("div", { class: "value" }, pct(live.ram_percent)),
        bar(live.ram_percent, "ram"),
        el(
          "span",
          { class: "detail", text: `${num(live.ram_used_gb, 1)} / ${num(live.ram_total_gb, 1)} GB` },
        ),
        sparkline(history.ram, "#b48ead"),
      ),
      metricCard(
        "GPU",
        el("div", { class: "value" }, live.gpu_percent == null ? dash(null) : pct(live.gpu_percent)),
        live.gpu_percent == null ? null : bar(live.gpu_percent, "gpu"),
        el(
          "span",
          { class: "detail", text: live.gpu_percent == null ? live.gpu_note || "—" : deg(live.gpu_temp_c) },
        ),
        sparkline(history.gpu, "#a3be8c"),
      ),
      metricCard(
        "Network",
        el("div", { class: "value" }, rates ? `${num(live.net_recv_mbs, 2)}` : "…", el("span", { class: "unit", text: "MB/s ↓" })),
        null,
        el("span", { class: "detail", text: rates ? `↑ ${num(live.net_sent_mbs, 2)} MB/s` : "waiting for rates" }),
        sparkline(history.netIn, "#81a1c1"),
      ),
    );
    frag.append(grid);

    const lower = el("div", { class: "grid-2" });
    lower.append(
      el(
        "article",
        { class: "card" },
        el("h3", { text: "Disk I/O" }),
        el("p", { class: "detail", text: rates
          ? `read ${num(live.disk_read_mbs, 2)}  ·  write ${num(live.disk_write_mbs, 2)} MB/s`
          : "waiting for rates" }),
        sparkline(history.diskR, "#ebcb8b"),
      ),
    );
    if (live.battery_percent != null) {
      lower.append(
        el(
          "article",
          { class: "card metric" },
          el("h3", { text: "Battery" }),
          el("div", { class: "row" },
            el("div", { class: "value" }, pct(live.battery_percent)),
            el("span", { class: "detail", text: live.battery_plugged ? "AC" : "battery" }),
          ),
          bar(live.battery_percent, "bat"),
        ),
      );
    }
    if (live.swap_total_gb) {
      lower.append(
        el(
          "article",
          { class: "card metric" },
          el("h3", { text: "Swap" }),
          el("div", { class: "row" },
            el("div", { class: "value" }, pct(live.swap_percent)),
            el("span", { class: "detail", text: `${num(live.swap_used_gb, 1)} / ${num(live.swap_total_gb, 1)} GB` }),
          ),
          bar(live.swap_percent, "ram"),
        ),
      );
    }
    frag.append(lower);
    return frag;
  }

  function renderCpu(payload) {
    const d = dataOf(payload, "cpu");
    if (!d) return fail(payload);
    const frag = document.createDocumentFragment();
    frag.append(pageHead(PAGES.cpu));
    frag.append(
      el(
        "article",
        { class: "card metric" },
        el("h3", { text: d.name || "Processor" }),
        el("div", { class: "row" },
          el("div", { class: "value" }, pct(d.usage_percent)),
          el("span", { class: "detail", text: `${deg(d.temp_c)}  ·  load ${dash(d.load_1m)}` }),
        ),
        bar(d.usage_percent, "cpu"),
        sparkline(history.cpu, "#88c0d0"),
      ),
    );
    const cores = d.usage_per_core || [];
    if (cores.length) {
      const box = el("article", { class: "card" }, el("h3", { text: "Per core" }));
      const grid = el("div", { class: "cores" });
      cores.forEach((v, i) => {
        grid.append(
          el(
            "div",
            { class: "core" },
            el("span", { text: String(i) }),
            bar(v, "cpu"),
            el("span", { text: pct(v) }),
          ),
        );
      });
      box.append(grid);
      frag.append(box);
    }
    frag.append(
      el(
        "article",
        { class: "card" },
        props([
          ["Cores", [d.cores_physical, d.cores_logical].filter((x) => x != null).join(" / ") || null],
          ["Clock", d.freq_current_mhz != null ? `${num(d.freq_current_mhz, 0)} MHz` : null],
          ["Max", d.freq_max_mhz != null ? `${num(d.freq_max_mhz, 0)} MHz` : null],
        ]),
      ),
    );
    return frag;
  }

  function renderGpu(payload) {
    const d = dataOf(payload, "gpu");
    if (!d) return fail(payload);
    const frag = document.createDocumentFragment();
    frag.append(pageHead(PAGES.gpu));
    const devices = d.devices || [];
    if (!devices.length) {
      frag.append(el("article", { class: "card" }, note("No GPU found.")));
      return frag;
    }
    for (const g of devices) {
      const vramPct =
        g.vram_total_mb && g.vram_used_mb != null
          ? (100 * Number(g.vram_used_mb)) / Number(g.vram_total_mb)
          : null;
      const card = el("article", { class: "card stack" });
      card.append(el("p", { class: "gpu-name", text: g.name || g.full_name || "GPU" }));
      if (g.usage_percent == null && g.note) card.append(note(g.note));
      else {
        card.append(
          el("p", { class: "detail", text: "Load" }),
          el("div", { class: "row" },
            el("div", { class: "value" }, pct(g.usage_percent)),
            el("span", { class: "detail", text: deg(g.temp_c) }),
          ),
          bar(g.usage_percent, "gpu"),
        );
      }
      if (vramPct != null) {
        card.append(
          el("p", { class: "detail", text: `VRAM  ${num(g.vram_used_mb, 0)} / ${num(g.vram_total_mb, 0)} MB` }),
          bar(vramPct, "gpu"),
        );
      }
      card.append(
        props([
          ["Vendor", g.vendor],
          ["Power", g.power_watts != null ? `${num(g.power_watts, 0)} W` : null],
          ["Limit", g.power_limit_watts != null ? `${num(g.power_limit_watts, 0)} W` : null],
          ["Graphics", g.graphics_mhz != null ? `${num(g.graphics_mhz, 0)} MHz` : null],
          ["Memory clock", g.mem_mhz != null ? `${num(g.mem_mhz, 0)} MHz` : null],
          ["PCI", g.pci_slot],
        ]),
      );
      frag.append(card);
    }
    return frag;
  }

  function renderMemory(payload) {
    const d = dataOf(payload, "memory");
    if (!d) return fail(payload);
    const ram = d.ram || {};
    const swap = d.swap || {};
    const frag = document.createDocumentFragment();
    frag.append(pageHead(PAGES.memory));
    frag.append(
      el(
        "article",
        { class: "card metric" },
        el("h3", { text: "RAM" }),
        el("div", { class: "row" },
          el("div", { class: "value" }, pct(ram.percent)),
          el("span", { class: "detail", text: `${num(ram.used_gb, 1)} / ${num(ram.total_gb, 1)} GB used` }),
        ),
        bar(ram.percent, "ram"),
        sparkline(history.ram, "#b48ead"),
      ),
    );
    if (swap.total_gb) {
      frag.append(
        el(
          "article",
          { class: "card metric" },
          el("h3", { text: "Swap" }),
          el("div", { class: "row" },
            el("div", { class: "value" }, pct(swap.percent)),
            el("span", { class: "detail", text: `${num(swap.used_gb, 1)} / ${num(swap.total_gb, 1)} GB` }),
          ),
          bar(swap.percent, "ram"),
        ),
      );
    }
    return frag;
  }

  function renderStorage(payload) {
    const d = dataOf(payload, "disk");
    if (!d) return fail(payload);
    const rates = d.rates_mbs || {};
    const frag = document.createDocumentFragment();
    frag.append(pageHead(PAGES.storage));
    frag.append(
      el(
        "article",
        { class: "card" },
        el("h3", { text: "Throughput" }),
        el("p", { class: "detail", text: `read ${num(rates.read, 2)}  ·  write ${num(rates.write, 2)} MB/s` }),
        sparkline(history.diskR, "#ebcb8b"),
      ),
    );
    const parts = d.partitions || [];
    if (parts.length) {
      const wrap = el("article", { class: "card" }, el("h3", { text: "Mounts" }));
      const table = el("table");
      table.append(
        el("thead", null, el("tr", null, el("th", { text: "Mount" }), el("th", { text: "Use" }), el("th", { text: "FS" }))),
      );
      const tb = el("tbody");
      for (const p of parts) {
        tb.append(
          el(
            "tr",
            null,
            el("td", { text: p.mountpoint || p.device || "—" }),
            el(
              "td",
              null,
              el("span", { class: "mini-bar" }, bar(p.percent, "disk")),
              `${pct(p.percent)}  ·  ${num(p.used_gb, 1)}/${num(p.total_gb, 1)} GB`,
            ),
            el("td", { text: p.fstype || "—" }),
          ),
        );
      }
      table.append(tb);
      wrap.append(el("div", { class: "table-wrap" }, table));
      frag.append(wrap);
    }
    const disks = d.disks || [];
    if (disks.length) {
      frag.append(
        el(
          "article",
          { class: "card" },
          el("h3", { text: "Disks" }),
          props(disks.map((disk) => [
            disk.name || disk.device || "disk",
            [disk.size_gb != null ? `${disk.size_gb} GB` : null, disk.media, disk.device]
              .filter(Boolean)
              .join("  ·  "),
          ])),
        ),
      );
    }
    return frag;
  }

  function renderNetSlice(slice, payload) {
    const d = payload.data || {};
    if (slice === "connections") {
      const block = d.connections || {};
      const rows = block.connections || [];
      const wrap = el("article", { class: "card" }, el("h3", { text: `${block.total || rows.length} connections` }));
      if (block.note) wrap.append(note(block.note));
      const table = el("table");
      table.append(el("thead", null, el("tr", null,
        el("th", { text: "Proc" }), el("th", { text: "Local" }),
        el("th", { text: "Remote" }), el("th", { text: "State" }))));
      const tb = el("tbody");
      rows.slice(0, 250).forEach((c) => {
        tb.append(el("tr", { class: c.health ? `health-${c.health}` : "" },
          el("td", { text: c.process || "?" }),
          el("td", { text: c.local || "—" }),
          el("td", { text: c.remote || "—" }),
          el("td", { text: c.status || "—" })));
      });
      table.append(tb);
      wrap.append(el("div", { class: "table-wrap" }, table));
      if (rows.length > 250) wrap.append(note(`showing 250 of ${rows.length}`));
      return wrap;
    }
    if (slice === "listen") {
      const block = d.listeners || {};
      const rows = block.listeners || [];
      const wrap = el("article", { class: "card" }, el("h3", { text: "Listening" }));
      if (block.note) wrap.append(note(block.note));
      const table = el("table");
      table.append(el("thead", null, el("tr", null, el("th", { text: "Address" }), el("th", { text: "Process" }))));
      const tb = el("tbody");
      rows.forEach((r) => {
        tb.append(el("tr", null, el("td", { text: r.address || "—" }), el("td", { text: r.process || "?" })));
      });
      table.append(tb);
      wrap.append(el("div", { class: "table-wrap" }, table));
      return wrap;
    }
    if (slice === "wifi") {
      const block = d.wifi || {};
      const wrap = el("article", { class: "card" }, el("h3", { text: "Wi-Fi" }));
      if (!block.available) {
        wrap.append(note(block.note || "not available"));
        return wrap;
      }
      const active = block.active || {};
      const signalBits = [];
      if (active.signal != null) signalBits.push(`${active.signal}%`);
      if (active.signal_dbm != null) signalBits.push(`${active.signal_dbm} dBm`);
      wrap.append(props([
        ["SSID", active.ssid],
        ["Signal", signalBits.join("  ·  ") || null],
        ["Channel", active.channel != null ? `ch ${active.channel}` : null],
        ["Band", active.freq_mhz != null ? `${active.freq_mhz} MHz` : null],
        ["Security", active.security],
      ]));
      if (block.aps_on_channel && active.channel != null) {
        wrap.append(note(`${block.aps_on_channel} APs on ch ${active.channel}${block.aps_on_channel >= 4 ? " (busy)" : ""}`));
      }
      const nearby = (block.networks || []).filter((n) => !n.active && n.ssid &&
        !(n.ssid === active.ssid && n.channel === active.channel));
      if (nearby.length) {
        const table = el("table");
        table.append(el("thead", null, el("tr", null,
          el("th", { text: "SSID" }), el("th", { text: "Signal" }), el("th", { text: "Ch" }))));
        const tb = el("tbody");
        nearby.slice(0, 12).forEach((n) => {
          tb.append(el("tr", null,
            el("td", { text: n.ssid || "—" }),
            el("td", { text: n.signal != null ? `${n.signal}%` : "—" }),
            el("td", { text: n.channel != null ? String(n.channel) : "—" })));
        });
        table.append(tb);
        wrap.append(el("h3", { text: "Nearby" }), el("div", { class: "table-wrap" }, table));
      }
      return wrap;
    }
    if (slice === "public") {
      const block = d.public || {};
      return el("article", { class: "card" }, el("h3", { text: "Public IP" }),
        el("p", { class: "ident", text: block.address || block.note || "unavailable" }));
    }
    if (slice === "ping") {
      const block = d.ping || {};
      if (!block.available) {
        return el("article", { class: "card" }, el("h3", { text: "Gateway ping" }),
          note(block.note || "unavailable"));
      }
      return el("article", { class: "card" }, el("h3", { text: "Gateway ping" }), props([
        ["Target", block.target],
        ["Iface", block.interface],
        ["Loss", block.loss_percent != null ? `${block.loss_percent}%` : null],
        ["RTT", block.rtt_avg_ms != null ? `${block.rtt_avg_ms} ms` : null],
      ]));
    }
    return el("article", { class: "card" }, note("nothing to show"));
  }

  function renderNetwork(payload) {
    const d = dataOf(payload, "net");
    if (!d) return fail(payload);
    const rates = d.rates_mbs || {};
    const gw = d.gateway || {};
    const dns = d.dns || {};
    const frag = document.createDocumentFragment();
    frag.append(pageHead(PAGES.network));
    frag.append(
      el(
        "article",
        { class: "card metric" },
        el("h3", { text: "Throughput" }),
        el("div", { class: "row" },
          el("div", { class: "value" }, `${num(rates.recv, 2)}`, el("span", { class: "unit", text: "↓" })),
          el("span", { class: "detail", text: `↑ ${num(rates.sent, 2)} MB/s` }),
        ),
        sparkline(history.netIn, "#81a1c1"),
      ),
    );
    const nics = rates.per_nic || [];
    if (nics.length > 1) {
      frag.append(
        el(
          "article",
          { class: "card" },
          el("h3", { text: "Per interface" }),
          props(nics.map((n) => [
            n.name || "nic",
            `↓ ${num(n.recv, 2)}  ↑ ${num(n.sent, 2)} MB/s`,
          ])),
        ),
      );
    }
    frag.append(
      el(
        "article",
        { class: "card" },
        props([
          ["Gateway", gw.gateway ? `${gw.gateway}  ·  ${gw.interface || "—"}` : null],
          ["DNS", (dns.servers || []).join(", ") || dns.note],
        ]),
      ),
    );
    const addrs = d.addresses || [];
    if (addrs.length) {
      const table = el("table");
      table.append(el("thead", null, el("tr", null,
        el("th", { text: "Iface" }), el("th", { text: "Family" }), el("th", { text: "Address" }))));
      const tb = el("tbody");
      addrs.forEach((row) => {
        tb.append(el("tr", null,
          el("td", { text: row.interface || "—" }),
          el("td", { text: row.family || "ip" }),
          el("td", { text: `${row.address || "—"}${row.netmask ? " /" + row.netmask : ""}` })));
      });
      table.append(tb);
      frag.append(el("article", { class: "card" }, el("h3", { text: "Addresses" }), el("div", { class: "table-wrap" }, table)));
    }

    const actions = el("div", { class: "actions" });
    const slices = [
      ["connections", "connections"],
      ["listen", "listen"],
      ["wifi", "wifi"],
      ["ping", "ping gateway"],
      ["public", "public IP"],
    ];
    for (const [key, label] of slices) {
      actions.append(
        el("button", {
          type: "button",
          text: label,
          "aria-pressed": extra.netSlice === key,
          onclick: () => loadNetSlice(key),
        }),
      );
    }
    frag.append(el("article", { class: "card" },
      el("h3", { text: "More (on demand, same as the CLI)" }),
      note("connections / listen / wifi / ping / public are not polled — click when you want them."),
      actions,
    ));
    if (extra.netSlice && extra.netPayload) {
      frag.append(renderNetSlice(extra.netSlice, extra.netPayload));
    }
    return frag;
  }

  async function loadNetSlice(key) {
    extra.netSlice = key;
    extra.busy = true;
    paintBusy();
    try {
      extra.netPayload = await query(["net", key === "public" ? "public" : key]);
      extra.busy = false;
      lastError = null;
      setLive(true, false);
      redraw();
    } catch (err) {
      extra.busy = false;
      lastError = err.message || String(err);
      setLive(false, false);
      redraw();
    }
  }

  function pick(bundle, name) {
    return dataOf(bundle, name) || {};
  }

  function renderSensors(payload) {
    const temps = pick(payload, "temps");
    const fans = pick(payload, "fans");
    const bat = pick(payload, "battery");
    const frag = document.createDocumentFragment();
    frag.append(pageHead(PAGES.sensors));

    const tcard = el("article", { class: "card" }, el("h3", { text: "Temperatures" }));
    if (temps.cpu_c != null) tcard.append(bar(Math.min(100, Number(temps.cpu_c)), "temp"));
    const rows = [["CPU", deg(temps.cpu_c)]];
    for (const g of temps.gpus || []) {
      rows.push([g.name || "GPU", g.temp_c == null ? g.note || "—" : deg(g.temp_c)]);
    }
    for (const s of temps.all_sensors || []) {
      if (s.celsius == null) continue;
      const label = (s.label || s.sensor || "sensor").trim();
      rows.push([label, deg(s.celsius)]);
    }
    tcard.append(props(rows.slice(0, 24)));
    frag.append(tcard);

    const flist = fans.fans || [];
    const fcard = el("article", { class: "card" }, el("h3", { text: "Fans" }));
    if (!flist.length) fcard.append(note(fans.note || "No fan RPM/PWM reported"));
    else {
      fcard.append(props(flist.map((f) => [
        f.label || f.sensor || "fan",
        f.rpm != null ? `${f.rpm} RPM` : pct(f.percent),
      ])));
    }
    frag.append(fcard);

    const bcard = el("article", { class: "card" }, el("h3", { text: "Battery" }));
    if (!bat.present) bcard.append(note(bat.note || "No battery detected"));
    else {
      bcard.append(
        el("div", { class: "row" },
          el("div", { class: "value" }, pct(bat.percent)),
          el("span", { class: "detail", text: bat.power_plugged ? "AC" : "battery" }),
        ),
        bar(bat.percent, "bat"),
      );
      if (bat.secs_left) bcard.append(el("p", { class: "detail", text: `${fmtUptime(bat.secs_left)} left` }));
    }
    frag.append(bcard);
    return frag;
  }

  function renderSystem(payload) {
    const os = pick(payload, "os");
    const board = pick(payload, "board");
    const disp = pick(payload, "display");
    const up = pick(payload, "uptime");
    const ver = (extra.version && extra.version.data) || {};
    const sys = board.system || {};
    const mb = board.motherboard || {};
    const bios = board.bios || {};
    const frag = document.createDocumentFragment();
    frag.append(pageHead(PAGES.system));
    frag.append(
      el("article", { class: "card" }, el("h3", { text: "OS" }), props([
        ["Distro", os.pretty_name || os.name],
        ["Kernel", os.kernel || os.release],
        ["Host", os.hostname],
        ["Desktop", os.desktop_environment],
        ["Session", os.session_type],
        ["Arch", os.architecture || os.machine],
        ["Uptime", up.human || fmtUptime(up.uptime_seconds)],
      ])),
      el("article", { class: "card" }, el("h3", { text: "Board" }), props([
        ["Machine", sys.name],
        ["Motherboard", mb.name],
        ["BIOS", bios.name || bios.version],
        ["BIOS date", bios.date],
      ])),
    );
    const displays = disp.displays || [];
    const dcard = el("article", { class: "card" }, el("h3", { text: "Displays" }));
    if (!displays.length) dcard.append(note(disp.note || "No connected display found."));
    else {
      dcard.append(props(displays.map((m) => {
        const bits = [];
        if (m.width && m.height) bits.push(`${m.width}×${m.height}`);
        if (m.refresh_hz != null) bits.push(fmtHz(m.refresh_hz));
        if (m.name) bits.push(m.name);
        return [m.connector || m.kind || "output", bits.join("  ·  ")];
      })));
    }
    frag.append(dcard);
    frag.append(
      el("article", { class: "card" }, el("h3", { text: "This app" }), props([
        ["Name", ver.name],
        ["Version", ver.version],
        ["CLI", ver.cli],
      ])),
    );

    const scanBox = el("article", { class: "card" }, el("h3", { text: "Inventory scan" }));
    scanBox.append(note("Same as si scan — click once, not polled."));
    scanBox.append(el("button", { type: "button", text: extra.scan ? "Scan again" : "Scan hardware", onclick: loadScan }));
    if (extra.scan) {
      const s = extra.scan.data || {};
      const sum = s.summary || {};
      const counts = s.counts || {};
      scanBox.append(props([
        ["Host", sum.hostname],
        ["OS", sum.os],
        ["CPU", sum.cpu],
        ["GPU", (sum.gpus || []).join(", ")],
        ["RAM", sum.ram_gb != null ? `${sum.ram_gb} GB` : null],
        ["Items", counts.total_components],
      ]));
    }
    frag.append(scanBox);
    return frag;
  }

  async function loadScan() {
    extra.busy = true;
    paintBusy();
    try {
      extra.scan = await query(["scan"]);
      extra.busy = false;
      lastError = null;
      setLive(true, false);
      redraw();
    } catch (err) {
      extra.busy = false;
      lastError = err.message || String(err);
      setLive(false, false);
      redraw();
    }
  }

  function fail(payload) {
    const err = (payload && payload.error) || lastError || "no data";
    return el("article", { class: "card" }, el("p", { class: "error", text: err }));
  }

  const RENDER = {
    overview: renderOverview,
    cpu: renderCpu,
    gpu: renderGpu,
    memory: renderMemory,
    storage: renderStorage,
    network: renderNetwork,
    sensors: renderSensors,
    system: renderSystem,
  };

  let lastPayload = null;

  function paintBusy() {
    if (!main.querySelector(".busy-flag")) {
      const flag = el("p", { class: "note busy-flag", text: "working…" });
      main.prepend(flag);
    }
  }

  function redraw() {
    const info = PAGES[page];
    navLinks.forEach((a) => {
      const on = a.dataset.page === page;
      if (on) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    });
    main.replaceChildren();
    if (lastError && !lastPayload) {
      main.append(el("article", { class: "card" }, el("p", { class: "error", text: lastError }),
        note("Is the terminal still running si gui?")));
      return;
    }
    const fn = RENDER[page];
    if (!fn || !lastPayload) {
      main.append(el("p", { class: "muted", text: "Loading…" }));
      return;
    }
    main.append(fn(lastPayload));
  }

  async function tick() {
    const info = PAGES[page];
    if (!info) return;
    try {
      const payload = await query(info.tokens);
      lastPayload = payload;
      lastError = null;
      if (page === "overview" || payload.resource === "status") rememberStatus(payload);
      if (page === "system") {
        try {
          extra.version = await query(["version"]);
        } catch (_) {
          extra.version = null;
        }
      }
      if (page === "cpu") {
        const d = dataOf(payload, "cpu") || {};
        push("cpu", d.usage_percent);
      }
      if (page === "memory") {
        const d = dataOf(payload, "memory") || {};
        push("ram", (d.ram || {}).percent);
      }
      if (page === "gpu") {
        const d = dataOf(payload, "gpu") || {};
        const g0 = (d.devices || [])[0] || {};
        push("gpu", g0.usage_percent);
      }
      if (page === "network") {
        const d = dataOf(payload, "net") || {};
        const rates = d.rates_mbs || {};
        push("netIn", rates.recv);
        push("netOut", rates.sent);
      }
      if (page === "storage") {
        const d = dataOf(payload, "disk") || {};
        const rates = d.rates_mbs || {};
        push("diskR", rates.read);
        push("diskW", rates.write);
      }
      setLive(true, false);
      redraw();
    } catch (err) {
      lastError = err.message || String(err);
      setLive(false, false);
      redraw();
    }
  }

  function startTimer() {
    stopTimer();
    tick();
    const info = PAGES[page];
    if (info && info.live && !document.hidden) {
      timer = setInterval(tick, INTERVAL_MS);
    }
  }

  function stopTimer() {
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
  }

  function setPage(id) {
    if (!PAGES[id]) id = "overview";
    page = id;
    extra.netSlice = null;
    extra.netPayload = null;
    lastPayload = null;
    if (location.hash !== `#${id}`) location.hash = id;
    startTimer();
  }

  navLinks.forEach((a) => {
    a.addEventListener("click", (ev) => {
      ev.preventDefault();
      setPage(a.dataset.page);
    });
  });

  window.addEventListener("hashchange", () => {
    const id = (location.hash || "#overview").slice(1);
    if (id !== page) setPage(id);
  });

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stopTimer();
    else startTimer();
  });

  query(["status"]).then(rememberStatus).catch(() => {});
  setPage((location.hash || "#overview").slice(1) || "overview");
})();
