"""Async API client for the Warmup cloud service."""
from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import urlparse

import aiohttp

_LOGGER = logging.getLogger(__name__)

_APP_TOKEN = 'M=;He<Xtg"$}4N%5k{$:PD+WA"]D<;#PriteY|VTuA>_iyhs+vA"4lic{6-LqNM:'
_BASE_HEADERS: dict[str, str] = {
    "user-agent": "WARMUP_APP",
    "accept-encoding": "br, gzip, deflate",
    "accept": "*/*",
    "Connection": "keep-alive",
    "content-type": "application/json",
    "app-token": _APP_TOKEN,
    "app-version": "1.8.1",
    "accept-language": "de-de",
}

_TOKEN_URL = "https://api.warmup.com/apps/app/v1"
_GRAPHQL_URL = "https://apil.warmup.com/graphql"

_GRAPHQL_QUERY = (
    "query QUERY{ user{ allLocations: locations { id name locModeInt "
    "rooms{ id roomName "
    "runModeInt targetTemp currentTemp awayTemp comfortTemp cost energy fixedTemp "
    "overrideTemp overrideDur roomModeInt sleepTemp schedule "
    "thermostat4ies{ id deviceSN "
    "minTemp maxTemp airTemp floor1Temp floor2Temp heatingTargetInt "
    "hasPolled isFaultAir isFaultFloor1 isFaultFloor2 } } } } }"
)

# Diagnostic-only schedule probe query — NOT used in normal polling.
# Fetches only location/room IDs plus the schedule field to minimise
# the risk of conflicting with unsupported fields in the normal query.
_SCHEDULE_PROBE_QUERY = (
    "query QUERY{ user{ allLocations: locations { id "
    "rooms{ id roomName schedule } } } }"
)

# GQL mutation to cancel an active override
_CANCEL_OVERRIDE_MUTATION = (
    "mutation QUERY{{room: cancelOverride(lid:{loc_id},rid:{room_id})"
    "{{ runModeInt targetTemp overrideTemp overrideDur }}}}"
)

# locModeInt → string mapping (LocationGQL.java)
LOC_MODE: dict[int, str] = {0: "auto", 1: "off", 2: "frost", 3: "timer"}
LOC_MODE_STR: dict[str, int] = {v: k for k, v in LOC_MODE.items()}

RUN_MODE: dict[int, str] = {
    0: "off",
    1: "prog",
    2: "override",
    3: "fixed",
    4: "frost",
    5: "away",
    6: "flip",
    7: "grad",
    8: "relay",
}
ROOM_MODE: dict[int, str] = {1: "prog", 3: "fixed"}
HEATING_TARGET: dict[int, str] = {0: "floor", 1: "air"}

# GQL returns day as an integer 0-6. Android Day.java ordinals: SUNDAY=0 … SATURDAY=6.
# Gson serialises the Day enum by name() (no @SerializedName, no registered adapter).
_DAY_INT_TO_NAME: list[str] = [
    "SUNDAY", "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY",
]


def gql_schedule_to_v1_groups(
    schedule: list,
    comfort_temp: str,
    setback_temp: str,
    sleep_temp: str,
) -> list[dict]:
    """Convert a GQL DayScheduleV2 list to Android V1 ProgramSchedule dicts.

    Each returned dict is the ``schedule`` object for one setProgramme call.
    Days that share identical (start, end) period patterns are merged into one
    group, matching EditProgramSelectedDaysFragment behaviour in the Android app.

    Field shapes proven by Android decompilation:
      comfortTemp/setbackTemp/sleepTemp  — 3-digit zero-padded string scalar
          (TemperatureJsonAdapter.write → jsonWriter.value(getServerTempInString()))
      sleepActive                        — "1"  (SimulateRoomDetailsV2JsonResponse.HEATING_TARGET)
      days                               — enum name strings, e.g. ["MONDAY", "TUESDAY"]
          (Gson default enum serialisation via name(); no Day type adapter registered)
      nodes[].temp                       — ""  (EditProgramSelectedDaysFragment:177
          programScheduleNode.setTemp(""); actual temps live at schedule level)

    Args:
        schedule:     raw list from the GQL ``schedule`` field.
        comfort_temp: 3-digit tenths string, e.g. "220" (= 22.0 °C).
        setback_temp: 3-digit tenths string, e.g. "160".
        sleep_temp:   3-digit tenths string, e.g. "180".
    """
    pattern_groups: dict[tuple, list[str]] = {}
    pattern_nodes: dict[tuple, list[dict]] = {}

    for entry in schedule:
        periods = entry.get("value", [])
        # Group by time-window signature only. Period temp is not part of the
        # V1 node shape (nodes always carry temp="").
        key = tuple((p["start"], p["end"]) for p in periods)
        day_name = _DAY_INT_TO_NAME[int(entry["day"])]
        pattern_groups.setdefault(key, []).append(day_name)
        if key not in pattern_nodes:
            pattern_nodes[key] = [
                {"start": p["start"], "end": p["end"], "temp": ""}
                for p in periods
            ]

    return [
        {
            "comfortTemp": comfort_temp,
            "setbackTemp": setback_temp,
            "sleepTemp": sleep_temp,
            "sleepActive": "1",
            "days": day_names,
            "nodes": pattern_nodes[key],
        }
        for key, day_names in pattern_groups.items()
    ]


def _url_path(url: str) -> str:
    """Return host+path of a URL without scheme or query string (safe to log)."""
    p = urlparse(url)
    return f"{p.netloc}{p.path}"


def _log_api_failure(
    operation: str,
    url: str,
    *,
    status: int | None = None,
    body: str | None = None,
    exc: BaseException | None = None,
    has_token: bool = False,
) -> None:
    """Log an API failure without leaking credentials."""
    parts = [f"WarmUp API failure: operation={operation}", f"endpoint={_url_path(url)}"]
    if status is not None:
        parts.append(f"status={status}")
    if exc is not None:
        parts.append(f"exc={type(exc).__name__}: {exc}")
    parts.append(f"auth_token_present={has_token}")
    if body:
        parts.append(f"body={body[:1000]}")
    _LOGGER.error(" | ".join(parts))


class WarmupAuthError(Exception):
    """Raised when credentials are rejected."""


class WarmupError(Exception):
    """Raised on API communication failures."""


class WarmupAPI:
    """Thin async wrapper around the Warmup cloud API."""

    def __init__(self, email: str, password: str, session: aiohttp.ClientSession) -> None:
        self._email = email
        self._password = password
        self._session = session
        self._token: str | None = None

    async def authenticate(self) -> None:
        """Obtain an access token; raises WarmupAuthError on bad credentials."""
        body: dict[str, Any] = {
            "request": {
                "email": self._email,
                "password": self._password,
                "method": "userLogin",
                "appId": "WARMUP-APP-V001",
            }
        }
        try:
            async with self._session.post(_TOKEN_URL, headers=_BASE_HEADERS, json=body) as resp:
                if resp.status != 200:
                    rb = await resp.text()
                    _log_api_failure("login", _TOKEN_URL, status=resp.status, body=rb, has_token=False)
                    raise WarmupAuthError(f"HTTP {resp.status}")
                data = await resp.json(content_type=None)
        except aiohttp.ClientError as exc:
            _log_api_failure("login", _TOKEN_URL, exc=exc, has_token=False)
            raise WarmupAuthError(str(exc)) from exc
        if data.get("status", {}).get("result") != "success":
            _log_api_failure(
                "login", _TOKEN_URL,
                body=str(data.get("response", {}))[:500],
                has_token=False,
            )
            raise WarmupAuthError("Invalid credentials")
        self._token = data["response"]["token"]

    async def fetch_locations(self) -> list[dict[str, Any]]:
        """Return all locations with rooms and thermostats."""
        if self._token is None:
            raise WarmupError("Not authenticated")
        headers = {**_BASE_HEADERS, "warmup-authorization": str(self._token)}
        try:
            async with self._session.post(
                _GRAPHQL_URL, headers=headers, json={"query": _GRAPHQL_QUERY}
            ) as resp:
                if resp.status != 200:
                    rb = await resp.text()
                    _log_api_failure("graphql", _GRAPHQL_URL, status=resp.status, body=rb, has_token=True)
                    raise WarmupError(f"HTTP {resp.status}")
                data = await resp.json(content_type=None)
        except aiohttp.ClientError as exc:
            _log_api_failure("graphql", _GRAPHQL_URL, exc=exc, has_token=True)
            raise WarmupError(str(exc)) from exc
        if data.get("errors"):
            _log_api_failure("graphql", _GRAPHQL_URL, body=str(data["errors"])[:500], has_token=True)
            raise WarmupError(f"GraphQL error: {data['errors']}")
        try:
            return data["data"]["user"]["allLocations"]
        except (KeyError, TypeError) as exc:
            _log_api_failure("graphql", _GRAPHQL_URL, body=str(data)[:500], exc=exc, has_token=True)
            raise WarmupError(f"Unexpected GQL response") from exc

    async def fetch_room_schedule(self, location_id: str, room_id: str) -> list | None:
        """Diagnostic probe: fetch schedule for one room without touching normal polling.

        Returns the raw schedule list from the Warmup API, or None if the field is
        missing/empty. Raises WarmupError on HTTP or GQL failure — caller must handle.
        Never called during setup or normal poll cycles.
        """
        if self._token is None:
            raise WarmupError("Not authenticated")
        headers = {**_BASE_HEADERS, "warmup-authorization": str(self._token)}
        try:
            async with self._session.post(
                _GRAPHQL_URL, headers=headers, json={"query": _SCHEDULE_PROBE_QUERY}
            ) as resp:
                if resp.status != 200:
                    rb = await resp.text()
                    _log_api_failure(
                        "schedule_probe", _GRAPHQL_URL,
                        status=resp.status, body=rb, has_token=True,
                    )
                    raise WarmupError(f"schedule probe HTTP {resp.status}")
                data = await resp.json(content_type=None)
        except aiohttp.ClientError as exc:
            _log_api_failure("schedule_probe", _GRAPHQL_URL, exc=exc, has_token=True)
            raise WarmupError(str(exc)) from exc
        if data.get("errors"):
            _log_api_failure(
                "schedule_probe", _GRAPHQL_URL,
                body=str(data["errors"])[:1000], has_token=True,
            )
            raise WarmupError(f"schedule probe GQL error: {data['errors']}")
        try:
            for loc in data["data"]["user"]["allLocations"]:
                if str(loc["id"]) == str(location_id):
                    for room in loc["rooms"]:
                        if str(room["id"]) == str(room_id):
                            return room.get("schedule") or None
        except (KeyError, TypeError) as exc:
            _log_api_failure(
                "schedule_probe", _GRAPHQL_URL,
                body=str(data)[:500], exc=exc, has_token=True,
            )
            raise WarmupError("Unexpected schedule probe response") from exc
        return None  # location/room not found in response

    async def set_location_mode(self, location_id: str, mode: str) -> None:
        """Set a location-level mode (e.g. 'frost', 'off')."""
        await self._post_control("setModes", {
            "account": {"email": self._email, "token": self._token},
            "request": {
                "method": "setModes",
                "values": {
                    "holEnd": "-", "fixedTemp": "", "holStart": "-",
                    "geoMode": "0", "holTemp": "-",
                    "locId": location_id, "locMode": mode,
                },
            },
        })

    async def set_temperature(self, room_id: str, mode: str, temperature: float | None = None) -> None:
        """Set room mode and optionally a fixed target temperature."""
        body: dict[str, Any] = {
            "account": {"email": self._email, "token": self._token},
            "request": {"method": "setProgramme", "roomId": room_id, "roomMode": mode},
        }
        if temperature is not None:
            body["request"]["fixed"] = {"fixedTemp": f"{int(temperature * 10):03d}"}
        await self._post_control("setProgramme", body)

    async def set_override(self, room_id: str, temperature: float, until: str) -> None:
        """Set a timed temperature override."""
        await self._post_control("setOverride", {
            "account": {"email": self._email, "token": self._token},
            "request": {
                "method": "setOverride",
                "rooms": [room_id],
                "temp": f"{int(temperature * 10):03d}",
                "until": until,
                "type": 3,
            },
        })

    async def cancel_override(self, location_id: str, room_id: str) -> None:
        """Cancel an active temperature override via GQL mutation (CTRL-3)."""
        if self._token is None:
            raise WarmupError("Not authenticated")
        mutation = _CANCEL_OVERRIDE_MUTATION.format(
            loc_id=location_id, room_id=room_id
        )
        headers = {**_BASE_HEADERS, "warmup-authorization": str(self._token)}
        try:
            async with self._session.post(
                _GRAPHQL_URL, headers=headers, json={"query": mutation}
            ) as resp:
                if resp.status != 200:
                    rb = await resp.text()
                    _log_api_failure("cancelOverride", _GRAPHQL_URL, status=resp.status, body=rb, has_token=True)
                    raise WarmupError(f"cancelOverride HTTP {resp.status}")
                data = await resp.json(content_type=None)
        except aiohttp.ClientError as exc:
            _log_api_failure("cancelOverride", _GRAPHQL_URL, exc=exc, has_token=True)
            raise WarmupError(str(exc)) from exc
        if data.get("errors"):
            _log_api_failure("cancelOverride", _GRAPHQL_URL, body=str(data["errors"])[:500], has_token=True)
            raise WarmupError(f"cancelOverride GQL error: {data['errors']}")

    async def set_schedule(
        self,
        room_id: str,
        schedule: list,
        comfort_temp: str,
        setback_temp: str,
        sleep_temp: str,
        *,
        dry_run: bool = False,
    ) -> list[dict]:
        """Write a weekly schedule via one setProgramme call per day-pattern group.

        ``comfort_temp``, ``setback_temp``, ``sleep_temp`` must be 3-digit
        zero-padded tenths-of-a-degree strings (e.g. "220" = 22.0 °C).
        Convert from a float via ``f"{int(temp * 10):03d}"``.

        When ``dry_run=True`` the payload is logged at WARNING level and no
        HTTP request is made.  Returns a list of request bodies (token redacted)
        so the caller can inspect or assert against the Android-proven shape.
        """
        groups = gql_schedule_to_v1_groups(schedule, comfort_temp, setback_temp, sleep_temp)

        redacted: list[dict] = []
        for sched in groups:
            body: dict[str, Any] = {
                "account": {"email": self._email, "token": self._token},
                "request": {
                    "method": "setProgramme",
                    "roomId": room_id,
                    "roomMode": "prog",
                    "schedule": sched,
                },
            }
            log_body = {**body, "account": {"email": self._email, "token": "***"}}
            redacted.append(log_body)
            if dry_run:
                _LOGGER.warning(
                    "set_schedule DRY RUN (not sent):\n%s",
                    json.dumps(log_body, indent=2),
                )
            else:
                await self._post_control("setProgramme", body)

        return redacted

    async def _post_control(self, operation: str, body: dict[str, Any]) -> None:
        try:
            async with self._session.post(_TOKEN_URL, headers=_BASE_HEADERS, json=body) as resp:
                if resp.status != 200:
                    rb = await resp.text()
                    _log_api_failure(operation, _TOKEN_URL, status=resp.status, body=rb, has_token=True)
                    raise WarmupError(f"HTTP {resp.status}")
                data = await resp.json(content_type=None)
        except aiohttp.ClientError as exc:
            _log_api_failure(operation, _TOKEN_URL, exc=exc, has_token=True)
            raise WarmupError(str(exc)) from exc
        if data.get("status", {}).get("result") != "success":
            _log_api_failure(operation, _TOKEN_URL, body=str(data.get("response", {}))[:500], has_token=True)
            raise WarmupError(f"Control command failed: {data.get('response', {})}")
