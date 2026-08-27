"""One collector pass per CLI query."""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.collectors import get_inventory, get_vitals
from backend.collectors.vitals import VITALS_ALL


@dataclass
class Snapshot:
    include_pci: bool = False
    verbose: bool = False
    vitals_needs: frozenset[str] = field(default_factory=lambda: VITALS_ALL)
    _inventory: dict | None = field(default=None, repr=False)
    _vitals: dict | None = field(default=None, repr=False)
    _net_connections: dict | None = field(default=None, repr=False)
    _net_listeners: dict | None = field(default=None, repr=False)
    _net_routes: dict | None = field(default=None, repr=False)
    _net_wifi: dict | None = field(default=None, repr=False)
    _net_public: dict | None = field(default=None, repr=False)
    _net_ping: dict | None = field(default=None, repr=False)

    def reuse_inventory(self, data: dict) -> None:
        """Use a previously collected inventory (live ticks skip lspci/DMI)."""
        self._inventory = data

    def peek_inventory(self) -> dict | None:
        """Inventory if already loaded this query; does not collect."""
        return self._inventory

    def inventory(self) -> dict:
        if self._inventory is None:
            self._inventory = get_inventory(include_pci=self.include_pci)
        return self._inventory

    def vitals(self) -> dict:
        if self._vitals is None:
            self._vitals = get_vitals(self.vitals_needs)
        return self._vitals

    def net_connections(self) -> dict:
        if self._net_connections is None:
            from backend.collectors.network import collect_connections

            self._net_connections = collect_connections()
        return self._net_connections

    def net_listeners(self) -> dict:
        if self._net_listeners is None:
            from backend.collectors.network import collect_listeners

            self._net_listeners = collect_listeners()
        return self._net_listeners

    def net_routes(self) -> dict:
        if self._net_routes is None:
            from backend.collectors.network import collect_routes

            self._net_routes = collect_routes()
        return self._net_routes

    def net_wifi(self) -> dict:
        if self._net_wifi is None:
            from backend.collectors.network import collect_wifi

            self._net_wifi = collect_wifi()
        return self._net_wifi

    def net_public_ip(self) -> dict:
        if self._net_public is None:
            from backend.collectors.network import collect_public_ip

            self._net_public = collect_public_ip()
        return self._net_public

    def net_ping(self) -> dict:
        if self._net_ping is None:
            from backend.collectors.network import collect_gateway_ping

            self._net_ping = collect_gateway_ping()
        return self._net_ping
