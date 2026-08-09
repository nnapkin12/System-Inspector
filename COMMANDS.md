# Command reference

Short terminal commands for **System Inspector**.

After [`./install.sh`](install.sh), you can run these from **any** directory — **no** desktop window or server needs to be running.

```bash
sysinspect <command>
si <command>          # same tool, shorter name
```

Need a reminder offline?

```bash
sysinspect help
```

---

## Quick start (after install)

```bash
sysinspect status
sysinspect gpu
sysinspect cpu temp
sysinspect temps
sysinspect motherboard
sysinspect watch gpu
```

---

## How commands work

You type **resources** (what you care about) and optional **fields** (how to filter the answer).

| Pattern | Example | Meaning |
|--------|---------|---------|
| resource | `gpu` | Full GPU info |
| resource + field | `gpu temp` | GPU temperatures only |
| several resources | `cpu gpu` | Both blocks |
| resources + field | `cpu gpu temp` | Temps for those resources |
| bare field | `temp` / `temps` | All main temperatures |

You do **not** need a separate command for every phrase — common words stack.

---

## Resources

| Type this | Also accepted | What you get |
|-----------|---------------|--------------|
| `status` | `summary` | Host overview + live CPU/GPU/RAM % and temps |
| `cpu` | `processor` | Model, load, cores, frequency, temp |
| `gpu` | `graphics`, `nvidia`, `vram` | Each GPU: load, VRAM, temp, power, driver |
| `ram` | `memory`, `mem` | Memory & swap usage |
| `temps` | `temp`, `thermal`, `temperature`, `temperatures` | CPU + GPU temperatures |
| `motherboard` | `board`, `mb`, `mobo`, `mainboard` | Machine, board, BIOS |
| `os` | `system`, `host`, `kernel` | Distro, kernel, desktop, hostname |
| `disk` | `storage`, `ssd`, `hdd`, `drive` | Disks, mounts, free space, I/O rates |
| `net` | `network`, `wifi`, `eth` | Interfaces + throughput |
| `battery` | `bat`, `power` | Charge % if a battery exists |
| `scan` | `inventory`, `hw`, `hardware` | Inventory summary |
| `all` | `everything`, `full` | Large combined snapshot |

---

## Fields (optional)

Put these **after** a resource (or alone for `temp` / `temps`):

| Type this | Also accepted | Effect |
|-----------|---------------|--------|
| `temp` | `temperature`, `temps` | Show temperatures only |
| `usage` | `util`, `load` | Show utilization only |
| `name` | `model` | Show names/models only |
| `summary` | | Shorter form (esp. with `scan`) |

---

## Examples

### Everyday checks

```bash
sysinspect status
sysinspect gpu
sysinspect cpu
sysinspect temps
sysinspect ram
sysinspect battery
```

### Combinations

```bash
sysinspect cpu temp
sysinspect gpu temp
sysinspect gpu usage
sysinspect cpu usage
sysinspect cpu gpu temp
sysinspect motherboard
sysinspect os
sysinspect disk
sysinspect net
sysinspect scan
sysinspect all
```

### Live refresh (terminal “monitor”)

```bash
sysinspect watch gpu
sysinspect watch temps
sysinspect watch cpu --interval 0.5
sysinspect watch status
```

Stop with **Ctrl+C**.

### JSON (for scripts)

```bash
sysinspect gpu --json
sysinspect cpu temp -j
sysinspect status --json
```

### Scan option

```bash
sysinspect scan
sysinspect scan --pci    # include full PCI device list (noisy)
```

---

## Options

| Flag | Meaning |
|------|---------|
| `--json` / `-j` | Print JSON instead of human text |
| `--pci` | With `scan`: include full PCI list |
| `--interval N` | With `watch`: seconds between updates (default `1`) |
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
