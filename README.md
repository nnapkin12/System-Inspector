#System Inspect

A terminal utility to monitor temperatures, loads, disks, network activity, and check hardware specs.

Run `si` or `sysinspect` from any folder — completely local

---

## Installation

```bash
git clone https://github.com/nnapkin12/System-Inspector.git
cd System-Inspector
./install.sh
```

`./install.sh` puts `si` and `sysinspect` into `~/.local/bin`.

If you get **command not found**, add that folder to your PATH once, then open a new terminal:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

---

## Usage Examples

### Components

```bash
si gpu             # GPU stats
si cpu             # CPU stats
si ram             # Memory/swap
si motherboard     # Board/ BIOS info
si battery         # laptop batt
si fans            # fans speed, sometimes not reported
si disk            # disks and free space
si scan            # full hardware specs scan
```

### Metrics, and other computer specs

```bash
si temps           # All hardware temperatures
si status          # system overview
si uptime          # uptime
si os              # kernel, desktop, distro
si version         # this app's version
```

### Target a specific component + its metric

```bash
si gpu temps
si cpu temps
si gpu load
si cpu load
```

### Live terminal refresh (monitor metrics)

```bash
si live gpu load              # GPU load
si live gpu temps             # GPU temperature
si live gpu cpu temps         # Combine multiple components and metrics
si live gpu --interval 0.5    # faster refresh / type 'faster' or 'slower' then Enter
```

While live mode is running, type `cpu`, `gpu`, or any component to switch — or type the full query like `net listen`.

---

## Network

```bash
si net                  # speed, gateway, DNS, your IP
si net connections      # active connections to your pc
si net listen           # listening ports
si net ip               # addresses per interface
si net wifi             # SSID + signal (laptops)
si net public           # public IP (needs internet)
```

colored text for connection health (green, yellow, red)

More commands: [COMMANDS.md](COMMANDS.md)

---

## Scripts / JSON

JSON straight from the CLI:

```bash
si gpu --json
si net connections --json
si scan --json --redact
```

`--redact` masks serials, UUIDs, boot_id, sku, and asset tags before printing (useful when sharing logs).

Other flags: `--plain` / `-p` · `--verbose` / `-v` · `--interval` · `--graph` · `--pci`

json for pretty much anything i just didnt want to type 20 examples
---

Local only · [MIT](LICENSE)
