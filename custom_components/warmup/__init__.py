"""The Warmup integration."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import WarmupAPI
from .const import DOMAIN
from .coordinator import WarmupCoordinator

_LOGGER = logging.getLogger(__name__)
_PLATFORMS = [Platform.CLIMATE, Platform.SENSOR, Platform.SELECT, Platform.BINARY_SENSOR]

_ATTR_UNTIL = "until"
_SERVICE_SET_OVERRIDE = "set_override"
_SERVICE_CANCEL_OVERRIDE = "cancel_override"
_SERVICE_SET_PROGRAMME = "set_programme"
_SERVICE_SCHEMA = vol.Schema({
    vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
    vol.Required(ATTR_TEMPERATURE): vol.Coerce(float),
    vol.Optional(_ATTR_UNTIL): cv.string,
})
_SERVICE_CANCEL_SCHEMA = vol.Schema({
    vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
})


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

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, _PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
