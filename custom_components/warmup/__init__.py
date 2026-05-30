"""The Warmup integration."""
from __future__ import annotations

import logging
import re as _re
from datetime import datetime, timedelta

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import WarmupAPI, WarmupError
from .const import DOMAIN
from .coordinator import WarmupCoordinator

_LOGGER = logging.getLogger(__name__)
_PLATFORMS = [Platform.CLIMATE, Platform.SENSOR, Platform.SELECT, Platform.BINARY_SENSOR]

_ATTR_UNTIL = "until"
_SERVICE_SET_OVERRIDE = "set_override"
_SERVICE_CANCEL_OVERRIDE = "cancel_override"
_SERVICE_SET_PROGRAMME = "set_programme"
_SERVICE_FETCH_SCHEDULE = "fetch_schedule_diagnostics"
_ATTR_SCHEDULE = "schedule"
_ATTR_DRY_RUN = "dry_run"
_SERVICE_COPY_SCHEDULE = "copy_current_schedule_template"
_SERVICE_SET_SCHEDULE = "set_schedule"
_SERVICE_SCHEMA = vol.Schema({
    vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
    vol.Required(ATTR_TEMPERATURE): vol.Coerce(float),
    vol.Optional(_ATTR_UNTIL): cv.string,
})
_SERVICE_CANCEL_SCHEMA = vol.Schema({
    vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
})

_HM = _re.compile(r"^\d{2}:\d{2}$")


def _validate_schedule(schedule: object, min_temp: float, max_temp: float) -> list:
    """Validate and normalise a schedule list. Returns cleaned list or raises ValueError."""
    if not isinstance(schedule, list) or len(schedule) != 7:
        raise ValueError(
            f"schedule must be a list of 7 day entries, got "
            f"{type(schedule).__name__} len={len(schedule) if isinstance(schedule, list) else '?'}"
        )
    result = []
    for entry in schedule:
        day = int(entry["day"])
        if not 0 <= day <= 6:
            raise ValueError(f"day must be 0-6, got {day}")
        periods = entry.get("value", [])
        if not isinstance(periods, list) or not periods:
            raise ValueError(f"day {day}: 'value' must be a non-empty list of periods")
        cleaned_periods = []
        prev_end = None
        for p in periods:
            start, end = p["start"], p["end"]
            if not (_HM.match(start) and _HM.match(end)):
                raise ValueError(f"day {day}: start/end must be HH:MM, got {start!r}/{end!r}")
            if start >= end:
                raise ValueError(f"day {day}: start {start} must be before end {end}")
            if prev_end is not None and start < prev_end:
                raise ValueError(
                    f"day {day}: period {start}-{end} overlaps previous ending {prev_end}"
                )
            raw_temp = p.get("temp")
            temp_c = int(raw_temp) / 10.0
            if not (min_temp <= temp_c <= max_temp):
                raise ValueError(
                    f"day {day}: temp {temp_c}°C outside thermostat range {min_temp}-{max_temp}°C"
                )
            cleaned_periods.append({"start": start, "end": end, "temp": raw_temp})
            prev_end = end
        result.append({
            "mode": str(entry.get("mode", "0")),
            "type": str(entry.get("type", "0")),
            "day": str(day),
            "node": str(entry.get("node", "2")),
            "value": cleaned_periods,
        })
    days_found = {int(e["day"]) for e in result}
    if days_found != set(range(7)):
        raise ValueError(
            f"schedule must have exactly days 0-6, found {sorted(days_found)}"
        )
    return result


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    api = WarmupAPI(entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD], session)
    await api.authenticate()

    coordinator = WarmupCoordinator(hass, api)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)

    async def handle_set_override(call: ServiceCall) -> None:
        entity_ids: list[str] = call.data[ATTR_ENTITY_ID]
        temperature: float = call.data[ATTR_TEMPERATURE]
        until: str = call.data.get(_ATTR_UNTIL, (datetime.now() + timedelta(hours=1)).strftime("%H:%M"))
        ent_reg = er.async_get(hass)
        for entry_coordinator in hass.data[DOMAIN].values():
            for sn, device in entry_coordinator.data.items():
                eid = ent_reg.async_get_entity_id("climate", DOMAIN, f"warmup_{sn}")
                if eid in entity_ids:
                    await entry_coordinator.api.set_override(device.room_id, temperature, until)
                    await entry_coordinator.async_request_refresh()

    if not hass.services.has_service(DOMAIN, _SERVICE_SET_OVERRIDE):
        hass.services.async_register(DOMAIN, _SERVICE_SET_OVERRIDE, handle_set_override, schema=_SERVICE_SCHEMA)

    async def handle_cancel_override(call: ServiceCall) -> None:
        entity_ids: list[str] = call.data[ATTR_ENTITY_ID]
        ent_reg = er.async_get(hass)
        for entry_coordinator in hass.data[DOMAIN].values():
            for sn, device in entry_coordinator.data.items():
                eid = ent_reg.async_get_entity_id("climate", DOMAIN, f"warmup_{sn}")
                if eid in entity_ids:
                    await entry_coordinator.api.cancel_override(device.location_id, device.room_id)
                    await entry_coordinator.async_request_refresh()

    if not hass.services.has_service(DOMAIN, _SERVICE_CANCEL_OVERRIDE):
        hass.services.async_register(DOMAIN, _SERVICE_CANCEL_OVERRIDE, handle_cancel_override, schema=_SERVICE_CANCEL_SCHEMA)

    async def handle_set_programme(call: ServiceCall) -> None:
        """Stub: schedule write is deferred — exact API body not live-tested."""
        raise ServiceValidationError(
            "warmup.set_programme is experimental and has not been live-tested. "
            "Use the Warmup app to edit schedules. "
            "Remove this guard once the API body format is confirmed against a real account."
        )

    if not hass.services.has_service(DOMAIN, _SERVICE_SET_PROGRAMME):
        hass.services.async_register(
            DOMAIN, _SERVICE_SET_PROGRAMME, handle_set_programme,
            schema=vol.Schema({vol.Required(ATTR_ENTITY_ID): cv.entity_ids}),
        )

    async def handle_fetch_schedule_diagnostics(call: ServiceCall) -> None:
        """Probe the Warmup API for schedule data on the targeted room.

        Does NOT affect normal polling or heating. Result is logged at WARNING
        level so it appears in HA logs without enabling debug mode.
        """
        entity_ids: list[str] = call.data[ATTR_ENTITY_ID]
        ent_reg = er.async_get(hass)
        matched = False
        for entry_coordinator in hass.data[DOMAIN].values():
            for sn, device in entry_coordinator.data.items():
                eid = ent_reg.async_get_entity_id("climate", DOMAIN, f"warmup_{sn}")
                if eid not in entity_ids:
                    continue
                matched = True
                _LOGGER.warning(
                    "WarmUp schedule probe: starting for room=%s (room_id=%s, location_id=%s)",
                    device.room_name, device.room_id, device.location_id,
                )
                try:
                    result = await entry_coordinator.api.fetch_room_schedule(
                        device.location_id, device.room_id
                    )
                except WarmupError as exc:
                    _LOGGER.warning(
                        "WarmUp schedule probe: FAILED for room=%s — %s",
                        device.room_name, exc,
                    )
                    continue
                if result is None:
                    _LOGGER.warning(
                        "WarmUp schedule probe: room=%s — API returned null/empty. "
                        "Schedule field may not be supported on this account or firmware, "
                        "or the room is not currently in programme mode.",
                        device.room_name,
                    )
                else:
                    _LOGGER.warning(
                        "WarmUp schedule probe: room=%s — schedule data received (%d entries): %s",
                        device.room_name, len(result) if isinstance(result, list) else 1, result,
                    )
        if not matched:
            _LOGGER.warning(
                "WarmUp schedule probe: no matching WarmUp device found for entity_id(s) %s",
                entity_ids,
            )

    if not hass.services.has_service(DOMAIN, _SERVICE_FETCH_SCHEDULE):
        hass.services.async_register(
            DOMAIN, _SERVICE_FETCH_SCHEDULE, handle_fetch_schedule_diagnostics,
            schema=vol.Schema({vol.Required(ATTR_ENTITY_ID): cv.entity_ids}),
        )

    async def handle_copy_schedule_template(call: ServiceCall) -> None:
        """Log the current schedule for the target room so user can copy it."""
        import json as _json
        entity_ids: list[str] = call.data[ATTR_ENTITY_ID]
        ent_reg = er.async_get(hass)
        matched = False
        for entry_coordinator in hass.data[DOMAIN].values():
            for sn, device in entry_coordinator.data.items():
                eid = ent_reg.async_get_entity_id("climate", DOMAIN, f"warmup_{sn}")
                if eid not in entity_ids:
                    continue
                matched = True
                if not device.schedule:
                    _LOGGER.warning(
                        "WarmUp schedule template: no schedule data for %s — "
                        "is the room in programme mode?",
                        eid,
                    )
                else:
                    _LOGGER.warning(
                        "WarmUp schedule template for %s (copy this to use with warmup.set_schedule):\n%s",
                        eid, _json.dumps(device.schedule, indent=2),
                    )
        if not matched:
            _LOGGER.warning(
                "WarmUp schedule template: no matching WarmUp device for %s", entity_ids
            )

    if not hass.services.has_service(DOMAIN, _SERVICE_COPY_SCHEDULE):
        hass.services.async_register(
            DOMAIN, _SERVICE_COPY_SCHEDULE, handle_copy_schedule_template,
            schema=vol.Schema({vol.Required(ATTR_ENTITY_ID): cv.entity_ids}),
        )

    async def handle_set_schedule(call: ServiceCall) -> None:
        entity_ids: list[str] = call.data[ATTR_ENTITY_ID]
        raw_schedule = call.data[_ATTR_SCHEDULE]
        dry_run: bool = call.data.get(_ATTR_DRY_RUN, True)
        ent_reg = er.async_get(hass)
        matched = False
        for entry_coordinator in hass.data[DOMAIN].values():
            for sn, device in entry_coordinator.data.items():
                eid = ent_reg.async_get_entity_id("climate", DOMAIN, f"warmup_{sn}")
                if eid not in entity_ids:
                    continue
                matched = True
                try:
                    validated = _validate_schedule(raw_schedule, device.min_temp, device.max_temp)
                except (ValueError, KeyError, TypeError) as exc:
                    _LOGGER.error("WarmUp set_schedule: validation FAILED for %s — %s", eid, exc)
                    raise ServiceValidationError(str(exc)) from exc

                # 3-digit zero-padded tenths strings required by TemperatureJsonAdapter.
                comfort_temp = f"{int(device.comfort_temperature * 10):03d}" if device.comfort_temperature else "200"
                setback_temp = f"{int(device.away_temperature * 10):03d}" if device.away_temperature else "160"
                sleep_temp   = f"{int(device.sleep_temperature * 10):03d}" if device.sleep_temperature else "160"

                _LOGGER.warning(
                    "WarmUp set_schedule %s for %s (room_id=%s) — "
                    "comfortTemp=%s setbackTemp=%s sleepTemp=%s",
                    "DRY RUN" if dry_run else "LIVE",
                    eid, device.room_id, comfort_temp, setback_temp, sleep_temp,
                )
                try:
                    await entry_coordinator.api.set_schedule(
                        device.room_id, validated,
                        comfort_temp, setback_temp, sleep_temp,
                        dry_run=dry_run,
                    )
                except WarmupError as exc:
                    _LOGGER.error("WarmUp set_schedule: API call FAILED for %s — %s", eid, exc)
                    raise ServiceValidationError(str(exc)) from exc

                if not dry_run:
                    await entry_coordinator.async_request_refresh()
                    _LOGGER.warning(
                        "WarmUp set_schedule: SUCCESS for %s — coordinator refreshed", eid
                    )
        if not matched:
            _LOGGER.warning(
                "WarmUp set_schedule: no matching WarmUp device for %s", entity_ids
            )

    if not hass.services.has_service(DOMAIN, _SERVICE_SET_SCHEDULE):
        hass.services.async_register(
            DOMAIN, _SERVICE_SET_SCHEDULE, handle_set_schedule,
            schema=vol.Schema({
                vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
                vol.Required(_ATTR_SCHEDULE): list,
                vol.Optional(_ATTR_DRY_RUN, default=True): bool,
            }),
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, _PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
