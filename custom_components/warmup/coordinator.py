"""DataUpdateCoordinator for the Warmup integration."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import WarmupAPI, WarmupError, RUN_MODE, ROOM_MODE, HEATING_TARGET, LOC_MODE
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
_SCAN_INTERVAL = timedelta(seconds=60)


@dataclass
class WarmupDevice:
    """Snapshot of a single Warmup thermostat and its room."""

    location_id: str
    location_name: str
    room_id: str
    room_name: str
    thermostat_id: str
    serial_number: str
    target_temperature: float = 0.0
    current_temperature: float = 0.0
    min_temp: float = 5.0
    max_temp: float = 35.0
    floor_temperature: float = 0.0
    floor_temperature_2: float = 0.0
    air_temperature: float = 0.0
    away_temperature: float = 0.0
    comfort_temperature: float = 0.0
    cost: str = "0"
    energy: str = "0"
    fixed_temperature: float = 0.0
    override_temperature: float = 0.0
    override_duration_mins: int = 0
    sleep_temperature: float = 0.0
    run_mode: str | None = None
    room_mode: str | None = None
    heating_target: str | None = None
    location_mode: str = "auto"
    has_polled: bool = False
    is_fault_air: bool = False
    is_fault_floor1: bool = False
    is_fault_floor2: bool = False


class WarmupCoordinator(DataUpdateCoordinator[dict[str, WarmupDevice]]):
    """Manages polling and distributes data to all Warmup entities."""

    def __init__(self, hass: HomeAssistant, api: WarmupAPI) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=_SCAN_INTERVAL)
        self.api = api

    async def _async_update_data(self) -> dict[str, WarmupDevice]:
        try:
            locations = await self.api.fetch_locations()
        except WarmupError as err:
            raise UpdateFailed(str(err)) from err

        devices: dict[str, WarmupDevice] = {}
        for location in locations:
            for room in location["rooms"]:
                for thermostat in room["thermostat4ies"]:
                    sn = thermostat["deviceSN"]
                    device = (self.data or {}).get(sn) or WarmupDevice(
                        location_id=location["id"],
                        location_name=location["name"],
                        room_id=room["id"],
                        room_name=room["roomName"],
                        thermostat_id=thermostat["id"],
                        serial_number=sn,
                    )
                    device.target_temperature = int(room["targetTemp"]) / 10
                    device.current_temperature = int(room["currentTemp"]) / 10
                    device.min_temp = int(thermostat["minTemp"]) / 10
                    device.max_temp = int(thermostat["maxTemp"]) / 10
                    device.floor_temperature = int(thermostat.get("floor1Temp") or 0) / 10
                    device.floor_temperature_2 = int(thermostat.get("floor2Temp") or 0) / 10
                    device.air_temperature = int(thermostat["airTemp"]) / 10
                    device.away_temperature = int(room["awayTemp"]) / 10
                    device.comfort_temperature = int(room["comfortTemp"]) / 10
                    device.cost = room["cost"]
                    device.energy = room["energy"]
                    device.fixed_temperature = int(room["fixedTemp"]) / 10
                    device.override_temperature = int(room["overrideTemp"]) / 10
                    device.override_duration_mins = int(room["overrideDur"])
                    device.sleep_temperature = int(room["sleepTemp"]) / 10
                    device.run_mode = RUN_MODE.get(room["runModeInt"])
                    device.room_mode = ROOM_MODE.get(room["roomModeInt"])
                    device.heating_target = HEATING_TARGET.get(thermostat["heatingTargetInt"])
                    # New fields from enhanced GQL query (use .get() for safety)
                    device.location_mode = LOC_MODE.get(location.get("locModeInt", 0), "auto")
                    device.has_polled = bool(thermostat.get("hasPolled", False))
                    device.is_fault_air = bool(thermostat.get("isFaultAir", False))
                    device.is_fault_floor1 = bool(thermostat.get("isFaultFloor1", False))
                    device.is_fault_floor2 = bool(thermostat.get("isFaultFloor2", False))
                    devices[sn] = device
        return devices
