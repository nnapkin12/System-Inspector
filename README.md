# System Inspector

See your PC’s hardware and live stats in the terminal — **CPU, GPU, temps, RAM, disks**, and more.

Works **offline** on Linux. Nothing is sent to the cloud. Great for checking temps while gaming or overclocking, or when you just want a quick system peek.

---

## Do I need to be a developer?

**No.** If you can open a terminal and paste a few commands, you can use this.

You do **not** need to know Python, APIs, or how servers work for the normal tools (`si status`, `si live`, etc.).

You only need a bit of Linux comfort:

1. Open a terminal  
2. Run install once  
3. Type short commands like `si temps`

---

## Install (once)

Open a terminal and paste:

```bash
git clone https://github.com/nnapkin12/System-Inspector.git
cd System-Inspector
./install.sh
```

That installs two commands you can use **any time, from any folder**:

| Type this | Same tool |
|-----------|-----------|
| `si` | short name (easiest) |
| `sysinspect` | longer name |

### If it says “command not found”

Paste this once, then open a **new** terminal:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### CLI only (no desktop menu icon)

```bash
./install.sh --cli-only
```

---

## First things to try

```bash
si status          # quick overview
si gpu             # graphics cards
si cpu             # processor
si temps           # temperatures
si live cpu gpu    # live bars (Ctrl+C to stop)
si help            # reminder inside the terminal
```

**Full list of commands:** [COMMANDS.md](https://github.com/nnapkin12/System-Inspector/blob/main/COMMANDS.md)

---

## Optional window / browser

Same data with a clickable window (not required for `si`):

```bash
./SystemInspector     # desktop window
./run.sh              # browser at http://127.0.0.1:8787
```

If the window opens in a browser instead of a real app, Ubuntu/linux may need:

```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.1
```

---

## Screenshots

![Scan](docs/scan.png)

![Utilization](docs/utilization.png)

![CPU detail](docs/cpu-detail.png)

---

Local only · no accounts · **MIT** ([LICENSE](LICENSE))
