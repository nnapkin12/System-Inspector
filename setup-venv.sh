# Shared by install.sh and ./sysinspect. Expects ROOT; cwd should be ROOT.
# shellcheck shell=bash

venv_has_pip() {
  [[ -x .venv/bin/python ]] && .venv/bin/python -m pip --version >/dev/null 2>&1
}

ensure_venv() {
  if venv_has_pip; then
    return 0
  fi
  if [[ -e .venv ]] && { [[ ! -w .venv ]] || [[ ! -w "$ROOT" ]]; }; then
    echo "error: .venv is incomplete and not writable (often left behind by sudo)." >&2
    echo "Fix with:" >&2
    echo "  sudo rm -rf \"$ROOT/.venv\"" >&2
    echo "  sudo chown -R \"\$USER:\$USER\" \"$ROOT\"" >&2
    echo "  ./install.sh" >&2
    return 1
  fi
  rm -rf .venv
  if ! python3 -m venv .venv; then
    echo "error: python3 -m venv failed." >&2
    echo "On Debian/Ubuntu/Pop!_OS:  sudo apt install python3-venv python3-pip" >&2
    return 1
  fi
  if ! venv_has_pip; then
    if ! .venv/bin/python -m ensurepip --upgrade >/dev/null; then
      echo "error: virtualenv has no pip." >&2
      echo "On Debian/Ubuntu/Pop!_OS:  sudo apt install python3-venv python3-pip" >&2
      echo "Then:  rm -rf .venv && ./install.sh" >&2
      return 1
    fi
  fi
}

install_python_deps() {
  .venv/bin/python -m pip install -q -U pip
  .venv/bin/python -m pip install -q -r "$ROOT/requirements.txt"
  # NVML bindings only matter on NVIDIA machines; AMD/Intel GPUs skip this.
  if command -v nvidia-smi >/dev/null 2>&1; then
    .venv/bin/python -m pip install -q "nvidia-ml-py>=12.0.0" || true
  fi
}
