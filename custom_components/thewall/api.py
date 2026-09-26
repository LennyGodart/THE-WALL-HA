"""Client for the Home Assistant API of a THE WALL server.

Home Assistant talks to the server, never to the device. The device polls the
server itself, so a command reaches the panel within about two seconds.
"""

from __future__ import annotations

import re
from typing import Any

import aiohttp
from yarl import URL

from .const import API_PATH

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=20)

_CODE_SEPARATORS = re.compile(r"[\s\-]+")


class TheWallError(Exception):
    """Base class for all errors of this client."""


class TheWallConnectionError(TheWallError):
    """The server could not be reached or did not answer like THE WALL."""


class TheWallApiError(TheWallError):
    """The server answered with an error envelope."""

    def __init__(
        self,
        status: int,
        code: str,
        messages: dict[str, str] | None = None,
        *,
        attempts_left: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        """Keep status, code and the messages in both languages."""
        self.status = status
        self.code = code
        self.messages = messages or {}
        self.attempts_left = attempts_left
        self.retry_after = retry_after
        text = self.messages.get("en", "")
        super().__init__(f"{code} (HTTP {status})" + (f": {text}" if text else ""))

    def message(self, language: str) -> str:
        """Return the server message in German or English, whichever fits."""
        lang = "de" if language.lower().startswith("de") else "en"
        return self.messages.get(lang) or self.messages.get("en") or self.code


class TheWallAuthError(TheWallApiError):
    """Token missing, wrong or revoked, or the device was deleted (HTTP 401)."""


class TheWallRateLimitError(TheWallApiError):
    """Too many requests (HTTP 429). retry_after holds the seconds to wait."""


def normalize_uid(value: str) -> str:
    """Return a device ID the way the server stores it."""
    return value.strip().lower()


def normalize_code(value: str) -> str:
    """Remove spaces and dashes and upper-case the pairing code."""
    return _CODE_SEPARATORS.sub("", value).upper()


def normalize_server(value: str) -> str | None:
    """Return the server URL without trailing slash, or None if it is not one."""
    value = value.strip()
    if not value:
        return None
    if "://" not in value:
        value = f"https://{value}"
    try:
        url = URL(value)
    except ValueError:
        return None
    if url.scheme not in ("http", "https") or not url.host:
        return None
    if url.query_string or url.fragment:
        return None
    return value.rstrip("/")


def _parse_retry_after(value: str | None) -> float | None:
    """Read Retry-After in seconds. An HTTP date is ignored."""
    if not value:
        return None
    try:
        seconds = float(value)
    except ValueError:
        return None
    return seconds if seconds > 0 else None


def _api_error(
    status: int, data: dict[str, Any], retry_after: float | None
) -> TheWallApiError:
    """Build the matching exception for an error envelope."""
    code = data.get("code")
    if not isinstance(code, str) or not code:
        code = "unknown"
    raw = data.get("error")
    messages: dict[str, str] = {}
    if isinstance(raw, dict):
        messages = {k: v for k, v in raw.items() if isinstance(v, str)}
    elif isinstance(raw, str):
        messages = {"en": raw}
    attempts = data.get("attempts_left")
    attempts_left = attempts if isinstance(attempts, int) else None
    cls: type[TheWallApiError] = TheWallApiError
    if status == 401 or code == "invalid_token":
        cls = TheWallAuthError
    elif status == 429 or code == "rate_limited":
        cls = TheWallRateLimitError
    return cls(
        status,
        code,
        messages,
        attempts_left=attempts_left,
        retry_after=retry_after,
    )


def _state_of(data: dict[str, Any]) -> dict[str, Any]:
    """Return the STATE object of a response, checking the parts entities need."""
    state = data.get("state")
    if (
        not isinstance(state, dict)
        or not isinstance(state.get("device"), dict)
        or not isinstance(state.get("panel"), dict)
    ):
        raise TheWallConnectionError("The server sent no valid state")
    return state


class TheWallClient:
    """Talk to /api/ha/v1 on a THE WALL server."""

    def __init__(
        self, session: aiohttp.ClientSession, server: str, token: str | None = None
    ) -> None:
        """Use the given session. Without a token only pairing works."""
        self._session = session
        self._base = server.rstrip("/") + API_PATH
        self._token = token

    async def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        auth: bool = True,
    ) -> dict[str, Any]:
        """Send one request and return the decoded success envelope."""
        headers = {"Accept": "application/json"}
        if auth:
            headers["Authorization"] = f"Bearer {self._token or ''}"
        if method == "POST" and payload is None:
            payload = {}
        try:
            async with self._session.request(
                method,
                f"{self._base}{path}",
                json=payload,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                status = resp.status
                retry_after = _parse_retry_after(resp.headers.get("Retry-After"))
                try:
                    data = await resp.json(content_type=None)
                except ValueError:
                    data = None
        except (aiohttp.ClientError, TimeoutError) as err:
            # A bare TimeoutError has no text, its name says enough.
            raise TheWallConnectionError(
                f"Cannot reach the server: {str(err) or type(err).__name__}"
            ) from err

        if not isinstance(data, dict):
            # No JSON envelope: this is not the API answering, except for the
            # two statuses a proxy in front of it may also send.
            if status == 401:
                raise TheWallAuthError(status, "invalid_token")
            if status == 429:
                raise TheWallRateLimitError(
                    status, "rate_limited", retry_after=retry_after
                )
            raise TheWallConnectionError(f"Unexpected answer (HTTP {status})")
        if status >= 400 or data.get("ok") is not True:
            raise _api_error(status, data, retry_after)
        return data

    async def pair(self, uid: str) -> dict[str, Any]:
        """Ask the panel to show a pairing code.

        Returns pairing (32 hex), expires_in (seconds) and length.
        """
        data = await self._request("POST", "/pair", {"device": uid}, auth=False)
        if not isinstance(data.get("pairing"), str):
            raise TheWallConnectionError("The server sent no pairing")
        return data

    async def confirm_pairing(
        self, pairing: str, code: str, name: str
    ) -> dict[str, Any]:
        """Send the code from the panel. Returns token and state."""
        data = await self._request(
            "POST",
            "/pair/confirm",
            {"pairing": pairing, "code": normalize_code(code), "name": name},
            auth=False,
        )
        if not isinstance(data.get("token"), str):
            raise TheWallConnectionError("The server sent no token")
        _state_of(data)
        return data

    async def get_state(self) -> dict[str, Any]:
        """Return the current STATE."""
        return _state_of(await self._request("GET", "/state"))

    async def _command(
        self, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Send a command. The response always carries the new state."""
        data = await self._request("POST", path, payload)
        _state_of(data)
        return data

    async def set_panel(
        self,
        *,
        on: bool | None = None,
        bright: int | None = None,
        mode: str | None = None,
        rotation: list[str] | None = None,
    ) -> dict[str, Any]:
        """Switch the panel, set brightness, mode or rotation."""
        payload: dict[str, Any] = {}
        if on is not None:
            payload["on"] = on
        if bright is not None:
            payload["bright"] = bright
        if mode is not None:
            payload["mode"] = mode
        if rotation is not None:
            payload["rotation"] = rotation
        return await self._command("/panel", payload)

    async def set_note(self, line1: str, line2: str) -> dict[str, Any]:
        """Show a note with two lines."""
        return await self._command("/note", {"line1": line1, "line2": line2})

    async def hide_note(self) -> dict[str, Any]:
        """Take the note out of the front."""
        return await self._command("/note/hide")

    async def start_timer(
        self, seconds: int, label: str | None = None
    ) -> dict[str, Any]:
        """Start a timer. The response carries the new timer and the state."""
        payload: dict[str, Any] = {"seconds": seconds}
        if label:
            payload["label"] = label
        return await self._command("/timer", payload)

    async def cancel_timer(self, timer_id: str | None = None) -> dict[str, Any]:
        """Cancel one timer, or all of them without an ID."""
        return await self._command(
            "/timer/cancel", {"id": timer_id} if timer_id else {}
        )

    async def set_alarm(
        self,
        *,
        on: bool | None = None,
        time: str | None = None,
        days: list[int] | None = None,
    ) -> dict[str, Any]:
        """Change the alarm. Time is HH:MM, days are ISO weekdays."""
        payload: dict[str, Any] = {}
        if on is not None:
            payload["on"] = on
        if time is not None:
            payload["time"] = time
        if days is not None:
            payload["days"] = days
        return await self._command("/alarm", payload)

    async def stop_ringing(self) -> dict[str, Any]:
        """Dismiss ringing timers and the ringing alarm."""
        return await self._command("/ring/stop")

    async def update_firmware(self) -> dict[str, Any]:
        """Ask the device to install the newest firmware on its next poll."""
        return await self._command("/firmware/update")

    async def unlink(self) -> None:
        """Revoke this token."""
        await self._request("POST", "/unlink")
