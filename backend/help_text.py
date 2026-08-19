"""Full terminal help for `si` and `si help`."""

FULL_HELP = """
Type `si` in a terminal. Longer name works too: `sysinspect`.

Stuck?  si help

── Components ──────────────────────────────────────────────

  si gpu             GPU stats (load, temp, VRAM, power)
  si cpu             CPU stats (model, load, cores, freq, temp)
  si ram             memory / swap
  si motherboard     board / BIOS
  si battery         laptop battery (if present)
  si fans            fan speeds (sometimes not reported)
  si disk            disks and free space
  si scan            full hardware inventory

  Also: processor→cpu  graphics/nvidia/vram→gpu  memory/mem→ram
        board/mb/mobo→motherboard  bat→battery  fan/cooling→fans
        storage/ssd/drive→disk  inventory/hw/hardware→scan

── Metrics & system info ───────────────────────────────────

  si temps           all hardware temperatures
  si status          quick overview
  si uptime          how long the PC has been on
  si os              distro, kernel, desktop, hostname
  si version         this app's version

  Also: summary→status  temp/thermal→temps  up→uptime
        system/host→os  network/eth→net  ver/about→version

  OS one-liners:
    si os version    si kernel    si hostname
    si os desktop    si os arch

── Component + metric ──────────────────────────────────────

  si gpu temps       si cpu temps       si gpu load
  si cpu temp        si gpu temp        si cpu usage
  si gpu name        si cpu name        si cpu gpu temp

  Fields: temp/temps/temperature  load/usage/util  name/model

── Network ─────────────────────────────────────────────────

  si net                  overview (speed, gateway, DNS, IP)
  si net connections      one line per app (--verbose every socket)
  si net listen           listening ports
  si net ip               addresses per interface
  si net wifi             SSID + signal (laptops)
  si net dns              DNS servers
  si net gateway          default router
  si net routes           routing table
  si net public           public IP (needs internet)

  Also: network/eth→net  conn/conns/sockets→connections
        listening/ports→listen  wlan/wireless→wifi

  connections/listen may need sudo for full process names on some systems.
  connections are color-coded (green / yellow / red).

── Live refresh (default on a TTY) ─────────────────────────

  Sensors refresh by themselves. No need to type `live`:

  si gpu             si cpu temps         si status
  si temps           si ram               si net

  Snapshots (print once):  si os  si motherboard  si scan  si version
                           si net public  si net connections
  si gpu --once      one snapshot of a live-worthy command

  `si live …` still works. While live: type cpu / gpu / temps to switch
  · faster/slower · graph · ? help · Esc clears typing · Ctrl+C quit

── Flags ───────────────────────────────────────────────────

  --plain / -p       no color or meters (also forces a snapshot)
  --json / -j        JSON output (snapshot unless `si live … --json`)
  --once             one snapshot even for sensors
  --redact           mask serials, UUIDs, boot_id, sku (sharing / logs)
  --verbose / -v     every socket (connections)
  --interval 0.5     live refresh speed
  --graph            line charts in live mode
  --no-logo          hide the SI ASCII header (on by default)
  --pci              extra PCI detail with si scan

  si gpu --json   si gpu --once   si status --plain   si gpu --no-logo
""".strip()
