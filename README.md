# System Inspector

Local **hardware scanner** + **live system monitering** for Linux.

This is a one of the first projects i made with AI, the ui is not the best but it works for what i was intending on making it for, it will scan your PC for full hardware specs (CPU, GPU, motherboard, disks, …), then monitor utilization, temperatures, memory, disk I/O, and network throughput, in 2 sepereate tabs in a dark desktop UI. I am not familiar with prompting, but i will add my exact prompt below, the ai did not one shot this application, it first made me run a server and than i told it i wanted an application, and i got this.

Prompt: "ok so what could i build that could look at my systems internals, all of my hardware, my os, and you could click on each peice of hardware it picks up on in a card neatly, it would have a dropdown with data, meaning, if someone has some random nvidia and its some specific notebook gpu, the application would get it,? and than also, it would have a system monitor where you can see ALL vitals, that would be in a system monitor for gpu, cpu, stuff, temps, util %, but it would be good ui, maybe dark backround and make sure that the system scanner/vitals are in seperate tabs so that it isnt too cluttered...""

I wont paste the whole prompt but thats basically what i said, i am very new to artifical generating code literally making folders on my pc all by itslef, so i wanted to try this out and suprisingly it did very well atleast
- **No cloud, no accounts, local APIs**
- Data never leaves your machine (`127.0.0.1` only)
- Built with free open-source libraries only

> **Status:** WIP · Linux first (tested on Pop!_OS). Desktop window via pywebview; Windows packaging WIP maybe later.

## Features

| Area | What’s included |
|------|------------------|
| **System scan** | full list  · large hardware cards · expand for details · optional PCI list · export JSON |
| **Utilization** | Start/stop monitoring · CPU / GPU / RAM / temps · disk I/O · network · click-through graphs |
| **Discovery** | Dynamic (NVIDIA NVML, AMD/Intel via PCI, psutil, sysfs)  |
| **Desktop app** | Native window + local backend · optional OS menu entry |

---

## Requirements

- Linux (created on ubuntu-like distro)
- Python **3.10+**
- For GPU metrics: NVIDIA driver + `nvidia-smi` when using NVIDIA
- For the native window: system WebKit / GTK stack for [pywebview](https://pywebview.flowrl.com/) (falls back to your browser if missing)

---

## Quick start

```bash
git clone https://github.com/YOUR_USER/SystemInspector.git
cd SystemInspector

# App window (recommended)
./SystemInspector
```

First run creates a `.venv` and installs dependencies from `requirements.txt`.

### Optional: install to app menu

```bash
./install-desktop.sh
```

Then open **System Inspector** from your desktop’s application search.

### Dev / browser only

```bash
./run.sh
# open http://127.0.0.1:8787
```

---

## How it works

```
┌─────────────────────────────────────┐
│  System Inspector window (pywebview)│
│  or browser @ 127.0.0.1:8787        │
│           frontend/                 │
└─────────────────┬───────────────────┘
                  │ HTTP + WebSocket
┌─────────────────▼───────────────────┐
│  Python “main process”              │
│  desktop_app.py / uvicorn           │
│  backend/  · FastAPI routes         │
│  collectors/ · psutil, NVML, sysfs  │
└─────────────────────────────────────┘


---

## API (local only)

| Endpoint | Description |
|----------|-------------|
| `GET /` | UI |
| `GET /api/health` | Liveness |
| `GET /api/inventory` | Hardware / OS snapshot (`?include_pci=true`) |
| `GET /api/vitals` | One-shot live metrics |
| `WS /ws/vitals` | Live metrics ~1/s |

Binds **`127.0.0.1:8787`** only.

---

## Notes & limits

- **Fans:** Many laptops expose ACPI fan nodes that always read `0`. Those are hidden; real RPM/% is shown only when the kernel/NVML reports it.
- **Hybrid graphics:** Both discrete and integrated GPUs are discovered when present.
- **Permissions:** Some sensors appear only if the OS exposes them to your user (usual on desktop Linux).

---

## Roadmap (ideas)

- [ ] Optional hardware product images / catalog data
- [ ] Windows support

---

## Contributing

Issues and PRs welcome. 
