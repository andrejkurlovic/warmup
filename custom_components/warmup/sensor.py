"""Sensor platform for Warmup — exposes per-device temperature readings and energy data."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import WarmupCoordinator, WarmupDevice


@dataclass(frozen=True, kw_only=True)
class WarmupSensorDescription(SensorEntityDescription):
    value_fn: Callable[[WarmupDevice], float | str | None] = lambda _: None


_SENSORS: tuple[WarmupSensorDescription, ...] = (
    WarmupSensorDescription(
        key="floor_temperature",
        translation_key="floor_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda d: d.floor_temperature,
    ),
    WarmupSensorDescription(
        key="air_temperature",
        translation_key="air_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda d: d.air_temperature,
    ),
    WarmupSensorDescription(
        key="away_temperature",
        translation_key="away_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.away_temperature,
    ),
    WarmupSensorDescription(
        key="comfort_temperature",
        translation_key="comfort_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.comfort_temperature,
    ),
    WarmupSensorDescription(
        key="sleep_temperature",
        translation_key="sleep_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.sleep_temperature,
    ),
    WarmupSensorDescription(
        key="override_temperature",
        translation_key="override_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.override_temperature,
    ),
    WarmupSensorDescription(
        key="energy",
        translation_key="energy",
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.energy,
    ),
    WarmupSensorDescription(
        key="cost",
        translation_key="cost",
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.cost,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: WarmupCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        WarmupSensor(coordinator, sn, desc)
        for sn in coordinator.data
        for desc in _SENSORS
    )


class WarmupSensor(CoordinatorEntity[WarmupCoordinator], SensorEntity):
    """A single sensor reading from a Warmup thermostat."""

    _attr_has_entity_name = True
    entity_description: WarmupSensorDescription

    def __init__(self, coordinator: WarmupCoordinator, sn: str, description: WarmupSensorDescription) -> None:
        super().__init__(coordinator)
        self._sn = sn
        self.entity_description = description
        self._attr_unique_id = f"warmup_{sn}_{description.key}"

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
    def native_value(self) -> float | str | None:
        return self.entity_description.value_fn(self._device)
