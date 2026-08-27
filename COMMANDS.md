you:~$ si
   SYSTEM INSPECTOR  ·  local live vitals and hardware
             offline · Ctrl+C stops live


────────────────────────────────────────────────────────────────────────

(read the installation guide in README).

Type `si` in a terminal. Longer name works too: `sysinspect` (example: `sysinspect status`).

Stuck?

```bash
si help    # shows a description of cmds, etc. for help
```

---

## Components


```bash
si gpu             # GPU(s) stats (name, load, temp, VRAM, power)
si cpu             # CPU stats (model, load, cores, freq, temp)
si ram             # memory / swap
si motherboard     # board / BIOS info
si display         # connected displays (resolution, refresh Hz)
si battery         # laptop battery (if present)
si fans            # fan speeds (sometimes not reported)
si disk            # disks and free space
si scan            # full hardware inventory scan
```

Also works (same commands):

| second names | Original |
|----------|---------|
| `processor` | `cpu` |
| `graphics`, `nvidia`, `vram` | `gpu` |
| `memory`, `mem` | `ram` |
| `board`, `mb`, `mobo` | `motherboard` |
| `monitor`, `monitors`, `screen` | `display` |
| `bat` | `battery` |
| `fan`, `cooling` | `fans` |
| `storage`, `ssd`, `drive` | `disk` |
| `inventory`, `hw`, `hardware` | `scan` |

---

## Metrics, and Other computer specs


```bash
si temps           # all hardware temperatures (CPU + GPU(s))
si status          # quick system overview
si uptime          # how long the PC has been on
si os              # distro, kernel, desktop, hostname
si version         # this app's version (not the OS)
```

Use `si all --json` for a full machine dump (terminal default is JSON-heavy).

Also works:

| Second Name| Original |
|----------|---------|
| `summary` | `status` |
| `temp`, `thermal`, `temperature` | `temps` |
| `up` | `uptime` |
| `system`, `host` | `os` |
| `network`, `eth` | `net` |
| `ver`, `about` | `version` |
| `everything`, `full` | `all` |

### OS — one line at a time

```bash
si os version      # distro name only 
si kernel          # kernel line only
si hostname        # hostname only
si os desktop      # desktop session
si os arch         # CPU architecture
```

---

## Target a specific component + its metric

Narrow one component to a single metric:

```bash
si gpu temps
si cpu temps
si gpu load
si cpu load
```

More examples:

```bash
si cpu temp        # CPU temperature only
si gpu temp        # GPU temperature only
si gpu usage       # GPU load / VRAM only
si cpu usage       # CPU load only
si cpu gpu temp    # temps for both CPU and GPU
si gpu name        # GPU name/model only
si cpu name        # CPU name/model only
```

Field words (use after a component):

| Field | Also works | What you get |
|-------|------------|--------------|
| `temp` | `temps`, `temperature` | temperatures only |
| `load` | `usage`, `util` | utilization only |
| `name` | `model` | names/models only |

---

## Network

Local network info — interfaces, IPs, connections, DNS, routing, WiFi. Everything here is read from your machine except `public` (needs a internet lookup).

```bash
si net                  # overview (speed, gateway, DNS, IPv4 / IPv6)
si net connections      # connections to your pc — every socket
si net ip               # IPv4 / IPv6 addresses per interface
si net wifi             # SSID, signal, channel, nearby APs (nmcli)
```

More:

```bash
si net listen           # ports waiting for inbound connections
si net ping             # ping the default gateway (LAN, 3 packets)
si net dns              # DNS servers
si net gateway          # default router
si net routes           # routing table
si net public           # your public IP (needs internet)
```

Also works:

| Second Name | Original |
|----------|---------|
| `network`, `eth` | `net` |
| `ips`, `ipv4`, `ipv6`, `addresses` | `net ip` |
| `conn`, `conns`, `sockets` | `net connections` |
| `listening`, `ports` | `net listen` |
| `route`, `default` | `net gateway` |
| `nameservers`, `resolvers` | `net dns` |
| `routing` | `net routes` |
| `wlan`, `wireless` | `net wifi` |
| `ping`, `latency`, `rtt` | `net ping` |
| `publicip` | `net public` |

Notes:

- `connections` and `listen` may need `sudo` for a full process list on some systems.
- `connections` lines are color-coded (green / yellow / red); problem lines sort to the top. Use `--json` for CPU, RTT, and other raw fields.
- `wifi` uses NetworkManager (`nmcli`) when available; `iw` fills in dBm for the connected AP.
- `ping` is ICMP to your default gateway only — a LAN check, not a speedtest.
- `public` calls a simple IP service over HTTPS — the only command here that uses the internet.

Live monitoring (default on a TTY):

```bash
si net                  # upload/download meters (live)
si net --once           # one snapshot
```

---

## Live terminal refresh (default for sensors)

On an interactive terminal, sensor commands refresh every **1 second**. do not need `si live`.

```bash
si status                     # overview
si gpu load                   # GPU load
si gpu temps                  # GPU temperature
si gpu cpu temps              # combine multiple components and metrics
si cpu gpu                    # CPU + GPU load and temps
si temps                      # temperatures only
si gpu                        # GPU only
si gpu --interval 0.5         # faster refresh (0.5s)
si gpu --once                 # one snapshot
```

These are one snapshot: `si os`, `si motherboard`, `si display`, `si scan`, `si version`, `si uptime`, `si net public`, `si net connections`, `si net ping`, `si net wifi`.

`si live …` is still accepted.

Speed up monitoring, or type `faster` / `slower` then Enter while it's live.

Bars look like: `[████████░░░░░░]  42°C`

### While live is running

You can change which component you're monitoring while it's live — instead of restarting, just type words and press **Enter**:

| Command | output |
|----------|----------------|
| `cpu` | watch CPU only |
| `gpu` | watch GPU only |
| `cpu gpu` | watch CPU + GPU |
| `temps` | temperatures |
| `ram` / `disk` / `net` | those meters |
| `status` or `clear` | back to overview |
| `graph` / `graph cpu` | switch to graph-only plots |
| `bars` / `meters` | back to progress bars |
| `faster` / `slower` | change refresh speed |
| `quit` | leave live mode |

Or type the full `si (component) (metric)` style words to switch what you're watching.

Shortcuts:

- '?' — show help while live
- 'Esc' — clear what you were typing
- 'Ctrl+C' — quit

### Graphs (separate from bars)

Must say `graph` — regular `si status` / `si cpu` stay bars only. Output is Braille line plots, no meters. Samples are raw (not smoothed).

```bash
si graph
si graph cpu
si graph gpu temp
si cpu gpu --graph
si gpu --graphs
```

While live, type `graph` or `graph cpu` then Enter. Type `bars` to return to meters.

---

## Optional web UI

A small local page. Not a replacement for the CLI.

```bash
si gui
si web              # same
si gui --port 8000
si gui --redact     # mask serials / UUIDs in the page
```

It prints a link (`http://127.0.0.1:8000`). Paste that in a browser. Ctrl+C in the terminal stops the server. Nothing listens on a port unless you run this.

---

## Flags

Add these to any command:

| Flag | What it does |
|------|----------------|
| `--plain` or `-p` | plain text only (no colors / banner / meters) |
| `--json` or `-j` | machine-readable JSON for scripts |
| `--redact` | mask serials, UUIDs, boot_id, sku, asset tags (logs / sharing) |
| `--verbose` or `-v` | extra JSON fields (connections always list every socket) |
| `--once` | one snapshot even for sensors (cpu, gpu, temps, …) |
| `--interval 0.5` | live update every half second |
| `--graph` / `--graphs` | graph-only Braille plots (no bars) |
| `--no-logo` | hide the System Inspector ASCII header (shown by default) |
| `--pci` | with `si scan`, list more PCI devices (long) |
| `--port 8000` | listen port for `si gui` (localhost only) |

```bash
si status --plain
si gpu --json
si gpu --no-logo
si scan --json --redact
si scan --pci
si net connections --json
si cpu gpu --interval 0.5 --graph
si live cpu gpu --graph
```

---

## Program names

| Name | Notes |
|------|--------|
| `si` | short |
| `sysinspect` | longer name, same tool |

Installed by `./install.sh` into `~/.local/bin`.

From the project folder **without** install:

```bash
./si gpu
./sysinspect status
```

---

## Uninstall the terminal commands

```bash
rm -f ~/.local/bin/sysinspect ~/.local/bin/si
```

(Does not delete the project folder.)

---

## JSON (scripts)

```bash
si gpu --json
si status --json
si net connections --json
si scan --json --redact
```
