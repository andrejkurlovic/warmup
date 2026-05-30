"""Select platform for Warmup — location mode (auto/off/frost/timer)."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import WarmupCoordinator, WarmupDevice

_OPTIONS = ["auto", "off", "frost", "timer"]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: WarmupCoordinator = hass.data[DOMAIN][entry.entry_id]
    # One select per unique location (not per thermostat)
    seen_locations: set[str] = set()
    entities = []
    for sn, device in coordinator.data.items():
        if device.location_id not in seen_locations:
            seen_locations.add(device.location_id)
            entities.append(WarmupLocationModeSelect(coordinator, sn))
    async_add_entities(entities)


class WarmupLocationModeSelect(CoordinatorEntity[WarmupCoordinator], SelectEntity):
    """Select entity representing the location heating mode."""

    _attr_has_entity_name = True
    _attr_translation_key = "location_mode"
    _attr_options = _OPTIONS

    def __init__(self, coordinator: WarmupCoordinator, serial_number: str) -> None:
        super().__init__(coordinator)
        self._sn = serial_number
        d = coordinator.data[serial_number]
        self._attr_unique_id = f"warmup_{d.location_id}_location_mode"

    @property
    def _device(self) -> WarmupDevice:
        return self.coordinator.data[self._sn]

    @property
    def device_info(self) -> DeviceInfo:
        d = self._device
        return DeviceInfo(
            identifiers={(DOMAIN, self._sn)},
            name=d.room_name,
            manufacturer="Warmup",
            model="4iE",
            serial_number=self._sn,
        )

    @property
    def current_option(self) -> str:
        mode = self._device.location_mode
        return mode if mode in _OPTIONS else "auto"

    async def async_select_option(self, option: str) -> None:
        """Set the location mode."""
        await self.coordinator.api.set_location_mode(self._device.location_id, option)
        await self.coordinator.async_request_refresh()
