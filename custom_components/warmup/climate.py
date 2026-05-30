"""Climate platform for Warmup thermostats."""
from __future__ import annotations

import json
from typing import Any

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACAction, HVACMode
from homeassistant.components.climate.const import PRESET_AWAY, PRESET_HOME
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, PRECISION_HALVES, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONST_MODE_AWAY, CONST_MODE_FIXED, CONST_MODE_FROST,
    CONST_MODE_OFF, CONST_MODE_PROGRAM, DOMAIN,
)
from .coordinator import WarmupCoordinator, WarmupDevice

_HVAC_MAP = {
    CONST_MODE_PROGRAM: HVACMode.AUTO,
    CONST_MODE_FIXED: HVACMode.HEAT,
    CONST_MODE_AWAY: HVACMode.AUTO,
    CONST_MODE_FROST: HVACMode.HEAT,
    CONST_MODE_OFF: HVACMode.OFF,
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: WarmupCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(WarmupClimate(coordinator, sn) for sn in coordinator.data)


class WarmupClimate(CoordinatorEntity[WarmupCoordinator], ClimateEntity):
    """Thermostat entity for one Warmup room."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = PRECISION_HALVES
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.AUTO, HVACMode.OFF]
    _attr_preset_modes = [PRESET_HOME, PRESET_AWAY]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, coordinator: WarmupCoordinator, serial_number: str) -> None:
        super().__init__(coordinator)
        self._sn = serial_number
        self._attr_unique_id = f"warmup_{serial_number}"

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
            suggested_area=d.room_name,
        )

    @property
    def current_temperature(self) -> float:
        return self._device.current_temperature

    @property
    def target_temperature(self) -> float:
        return self._device.target_temperature

    @property
    def min_temp(self) -> float:
        return self._device.min_temp

    @property
    def max_temp(self) -> float:
        return self._device.max_temp

    @property
    def hvac_mode(self) -> HVACMode:
        return _HVAC_MAP.get(self._device.run_mode, HVACMode.AUTO)

    @property
    def hvac_action(self) -> HVACAction:
        mode = self._device.run_mode
        if mode == CONST_MODE_OFF:
            return HVACAction.OFF
        if mode in (CONST_MODE_AWAY, CONST_MODE_FROST):
            return HVACAction.IDLE
        return HVACAction.HEATING

    @property
    def preset_mode(self) -> str:
        if self._device.run_mode in (CONST_MODE_AWAY, CONST_MODE_FROST):
            return PRESET_AWAY
        return PRESET_HOME

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        await self.coordinator.api.set_temperature(self._device.room_id, "fixed", temperature)
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self.coordinator.api.set_location_mode(self._device.location_id, "off")
        elif hvac_mode == HVACMode.AUTO:
            await self.coordinator.api.set_temperature(self._device.room_id, "prog")
        elif hvac_mode == HVACMode.HEAT:
            await self.coordinator.api.set_temperature(self._device.room_id, "fixed")
        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        if preset_mode == PRESET_HOME:
            await self.coordinator.api.set_temperature(self._device.room_id, "prog")
        elif preset_mode == PRESET_AWAY:
            await self.coordinator.api.set_location_mode(self._device.location_id, "frost")
        await self.coordinator.async_request_refresh()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose schedule as a JSON diagnostic attribute (read-only)."""
        schedule = self._device.schedule
        if schedule is not None:
            return {"schedule": schedule}
        return {}

    async def async_turn_on(self) -> None:
        await self.async_set_hvac_mode(HVACMode.AUTO)

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)
