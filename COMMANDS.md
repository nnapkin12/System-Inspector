# Command reference

List of terminal commands for **System Inspector**.

After [`./install.sh`](install.sh), you can run these from any directory, no window or server needs to be running.

```bash
si <command>
sysinspect <command>          # longer name if you want for some reason
```

Need a reminder offline?

```bash
sysinspect help
```

---

## Quick start (after install)

```bash
si status
si gpu
si cpu temp
si temps
si motherboard
si watch gpu
```

---

## How commands work

Type **resources** (a peice of hardware eg. 'cpu' 'gpu') and optional **fields** (how to filter the answer, weather you want its temp, util %, etc.).

| Pattern | Example | Meaning |
|--------|---------|---------|
| resource | `gpu` | Full GPU info |
| resource + field | `gpu temp` | GPU temperatures only |
| several resources | `cpu gpu` | Both CPU and GPU info |
| resources + field | `cpu gpu temp` | Temps for CPU and GPU |
| bare field | `temp` / `temps` | All temperatures |

 — common words stack.

---

## Resources

| Type this | Also accepted | What you get |
|-----------|---------------|--------------|
| `status` | `summary` | Host overview + live CPU/GPU/RAM % and temps |
| `cpu` | `processor` | Model, load, cores, frequency, temp |
| `gpu` | `graphics`, `nvidia`, `vram` | Each GPU: load, VRAM, temp, power, driver |
| `ram` | `memory`, `mem` | Memory & swap usage |
| `temps` | `temp`, `thermal`, `temperature`, `temperatures` | CPU + GPU temperatures |
| `fans` | `fan`, `cooling` | Fan RPM / PWM when reported |
| `motherboard` | `board`, `mb`, `mobo`, `mainboard` | Machine, board, BIOS |
| `os` | `system`, `host`, `kernel` | Distro, kernel, desktop, hostname |
| `disk` | `storage`, `ssd`, `hdd`, `drive` | Disks, mounts, free space, I/O rates |
| `net` | `network`, `wifi`, `eth` | Interfaces + throughput |
| `battery` | `bat`, `power` | Charge % if a battery exists |
| `scan` | `inventory`, `hw`, `hardware` | Inventory summary |
| `all` | `everything`, `full` | Large combined snapshot |

---

## Fields 

Put these **after** a resource (or alone for `temp` / `temps`):

| Type this | Also accepted | Effect |
|-----------|---------------|--------|
| `temp` | `temperature`, `temps` | Show temperatures only |
| `usage` | `util`, `load` | Show utilization only |
| `name` | `model` | Show names/models only |
| `summary` | | Shorter form (esp. with `scan`) |

---

## Examples

```bash
si status
si gpu
si cpu
si temps
si ram
si battery
```

### Combinations

```bash
si cpu temp
si gpu temp
si gpu usage
si cpu usage
si cpu gpu temp
si motherboard
si os
si disk
si net
si scan
si all
```

### Live refresh 

```bash
si live gpu
si live cpu gpu          # load + temp bars (best for OC)
si live temps
si live                  # status overview
si graph temps           # bars + optional line charts
si live gpu --graph      # same opt-in charts
```

Live mode is **large block bars** only by default (`[████░░░░░░]  38°C`). Use `graph` or `--graph` if you want history charts, but they are kinda clunky. Ctrl+C to stop.

### JSON (for scripts)

```bash
si gpu --json
si cpu temp -j
si status --plain --json
```

**`--plain` / `-p`** = text only (no banner, colors, meters). Best for pipes and logs.

### Scan your hardware

```bash
si scan
si scan --pci    # include full PCI device list (noisy)
```

---

## Options

| Flag | Meaning |
|------|---------|
| `--json` / `-j` | Print JSON instead of human text |
| `--plain` / `-p` | Text only — no banner, colors, meters |
| `--pci` | With `scan`: include full PCI list |
| `--interval N` | With `watch`: seconds between updates (default `1`) |
| `--graph` | With `watch`/`live`: also draw line charts (off by default) |
| `help` / `-h` / `--help` | Show in-terminal help |

---

## Aliases for the program name

| Name | Notes |
|------|--------|
| `sysinspect` | Main name |
| `si` | Short alias (same commands) |

Both are installed by `./install.sh` into `~/.local/bin`.

From the project folder without installing:

```bash
./sysinspect gpu
./si cpu temp
```

---

## HTTP API (optional)

The CLI is the main interface. If the **desktop app** or `./run.sh` is running, the same ideas exist over HTTP on `http://127.0.0.1:8787`:

| Request | Like CLI |
|---------|----------|
| `GET /api/status` | `sysinspect status` |
| `GET /api/cpu` | `sysinspect cpu` |
| `GET /api/gpu` | `sysinspect gpu` |
| `GET /api/memory` · `/api/ram` | `sysinspect ram` |
| `GET /api/temps` · `/api/temp` | `sysinspect temps` |
| `GET /api/board` · `/api/motherboard` | `sysinspect motherboard` |
| `GET /api/os` | `sysinspect os` |
| `GET /api/disk` · `/api/storage` | `sysinspect disk` |
| `GET /api/net` · `/api/network` | `sysinspect net` |
| `GET /api/battery` | `sysinspect battery` |
| `GET /api/scan` | `sysinspect scan` |
| `GET /api/all` | `sysinspect all` |
| `GET /api/query?q=gpu+temp` | `sysinspect gpu temp` |
| `GET /api/cpu?fields=temp` | `sysinspect cpu temp` |
| `GET /api/help` | help text |
| `GET /api/commands` | machine-readable command list |
| `GET /api/inventory` | full UI scan dump |
| `GET /api/vitals` | full live vitals dump |
| `WS /ws/vitals` | live stream for the UI |

```bash
curl -s http://127.0.0.1:8787/api/gpu | jq
curl -s 'http://127.0.0.1:8787/api/query?q=cpu+temp' | jq
```

The CLI does **not** need any of this — it reads the system itself.

---

## Uninstall CLI wrappers

```bash
rm -f ~/.local/bin/sysinspect ~/.local/bin/si
```
