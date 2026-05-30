"""Binary sensor platform for Warmup — thermostat fault diagnostics."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import WarmupCoordinator, WarmupDevice


@dataclass(frozen=True, kw_only=True)
class WarmupBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[WarmupDevice], bool] = lambda _: False


_FAULT_SENSORS: tuple[WarmupBinarySensorDescription, ...] = (
    WarmupBinarySensorDescription(
        key="fault_air",
        translation_key="fault_air",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.is_fault_air,
    ),
    WarmupBinarySensorDescription(
        key="fault_floor1",
        translation_key="fault_floor1",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.is_fault_floor1,
    ),
    WarmupBinarySensorDescription(
        key="fault_floor2",
        translation_key="fault_floor2",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.is_fault_floor2,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: WarmupCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        WarmupFaultSensor(coordinator, sn, desc)
        for sn in coordinator.data
        for desc in _FAULT_SENSORS
    )


class WarmupFaultSensor(CoordinatorEntity[WarmupCoordinator], BinarySensorEntity):
    """A fault diagnostic binary sensor for a Warmup thermostat."""

    _attr_has_entity_name = True
    entity_description: WarmupBinarySensorDescription

    def __init__(
        self,
        coordinator: WarmupCoordinator,
        sn: str,
        description: WarmupBinarySensorDescription,
    ) -> None:
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
    def is_on(self) -> bool:
        return self.entity_description.value_fn(self._device)
