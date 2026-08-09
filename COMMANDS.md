# Commands — System Inspector

After install (`./install.sh`), this works from **any folder** .

Type `si` in a terminal. Longer name works too: `sysinspect` (example: `sysinspect status`).

Stuck? Type:

```bash
si help
```

---

## Use cases

| Goal | Command |
|------|-----------|
| Quick overview of your PC | `si status` |
| GPU (name, load, temp, VRAM) | `si gpu` |
| CPU (model, load, speed, temp) | `si cpu` |
| Just temperatures | `si temps` |
| Memory / RAM | `si ram` |
| Disks and free space | `si disk` |
| Network activity | `si net` |
| Laptop battery | `si battery` |
| Motherboard / BIOS | `si motherboard` |
| OS version, hostname | `si os` |
| Fan speeds (if your laptop reports them) | `si fans` |
| Full hardware scan | `si scan` |
| How long the PC has been on | `si uptime` |
| This app's version | `si version` |
| **Live** bars that refresh | `si live` · e.g. `si live cpu gpu` |
| Stop live mode | press **Ctrl+C** |

---

## Examples

Copy any line:

```bash
si status
si gpu
si cpu
si temps
si ram
si battery
si motherboard
si disk
si net
si scan
```

### More detailed outputs

```bash
si cpu temp       # only CPU temperature
si gpu temp       # only GPU temperatures
si gpu usage      # only GPU load / VRAM
si cpu usage      # only CPU load
si cpu gpu temp   # temps for both
si os version     # only distro line (e.g. Pop!_OS 24.04 LTS)
si kernel         # only kernel line
si hostname       # only hostname
si uptime
si version        # System Inspector app version (not the OS)
```

Extra OS words (`version`, `kernel`, …) **do** narrow the answer — you don’t need a separate long command for each line.

---

## Live refresh

Live bars for a simple terminal UI:

```bash
si live                       # overview
si live cpu gpu               # CPU + GPU load and temps
si live temps                 # temperatures only
si live gpu                   # GPU only
si live gpu --interval 0.5    # faster refresh (0.5s)
```

- Bars look like: `[████████░░░░░░]  42°C`
- Default: refresh every **1 second** (change with `--interval`)
- Stop with **Ctrl+C**

### Line charts (optional — not default)

```bash
si graph temps
si live cpu --graph
```

---

## Extras

| Flag | What it does |
|------|----------------|
| `--plain` or `-p` | Plain text only (no colors / banner / meters) |
| `--json` or `-j` | Machine-readable JSON for scripts |
| `--interval 0.5` | Live update every half second |
| `--graph` | Add line charts in live mode |
| `--pci` | With `si scan`, list more PCI devices (long) |

Examples:

```bash
si status --plain
si gpu --json
si scan --pci
```

---

## Wording

Several words map to the same info.

### Hardware & sensors

| Type | Also works | Output |
|------|------------|--------|
| `status` | `summary` | Host + live RAM % and temps |
| `cpu` | `processor` | Model, load, cores, freq, temp |
| `gpu` | `graphics`, `nvidia`, `vram` | Load, VRAM, temp, power |
| `ram` | `memory`, `mem` | Memory and swap |
| `temps` | `temp`, `thermal` | CPU + GPU temperatures |
| `fans` | `fan`, `cooling` | Fan RPM/PWM if reported |
| `motherboard` | `board`, `mb`, `mobo` | Machine, board, BIOS |
| `os` | `system`, `host`, `kernel` | Distro, kernel, desktop |
| `disk` | `storage`, `ssd`, `drive` | Disks, space, I/O rates |
| `net` | `network`, `wifi` | Interfaces + throughput |
| `battery` | `bat` | Charge % (laptops) |
| `scan` | `inventory`, `hw`, `hardware` | Hardware summary |
| `uptime` | `up` | Time since boot |
| `version` | `ver`, `about` | System Inspector app version |
| `all` | `everything`, `full` | Large dump of almost everything |

### Filters

| Type after a resource | Effect |
|----------------------|--------|
| `temp` / `temperature` | Temperatures only |
| `usage` / `util` / `load` | Utilization only |
| `name` / `model` | Names/models only |
| `version` (with `os`) | Distro name only |
| `kernel` | Kernel only (`si kernel` alone works) |
| `hostname` | Hostname only |
| `desktop` / `de` | Desktop session |
| `arch` | CPU arch |

---

## Program names

| Name | Notes |
|------|--------|
| `si` | Short  |
| `sysinspect` | Longer name, same tool |

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

## For the desktop app (optional)

The terminal tool **doesnt** needs this.

If the desktop app or `./run.sh` is running, the same data is also available locally at `http://127.0.0.1:8787` for the UI / scripting.

| Request | Like CLI |
|---------|----------|
| `GET /api/status` | `si status` |
| `GET /api/cpu` | `si cpu` |
| `GET /api/gpu` | `si gpu` |
| `GET /api/memory` | `si ram` |
| `GET /api/temps` | `si temps` |
| `GET /api/board` | `si motherboard` |
| `GET /api/os` | `si os` |
| `GET /api/disk` | `si disk` |
| `GET /api/net` | `si net` |
| `GET /api/battery` | `si battery` |
| `GET /api/scan` | `si scan` |
| `GET /api/all` | `si all` |
| `GET /api/query?q=gpu+temp` | `si gpu temp` |
| `GET /api/help` | help text |

```bash
curl -s http://127.0.0.1:8787/api/gpu | jq
```

`si` is no server required.
