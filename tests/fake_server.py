"""An in-memory THE WALL server behind aioclient_mock.

It follows the API contract closely enough that entity tests can check both
the request and the state that comes back. Tests queue errors with fail() or
raw answers with respond().
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
import re
from typing import Any

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)
from yarl import URL

from custom_components.thewall.const import API_PATH, DEFAULT_SERVER

UID = "wall-7f3a91"
TOKEN = "twha_" + "A" * 43
NEW_TOKEN = "twha_" + "B" * 43
PAIRING = "0123456789abcdef0123456789abcdef"
CODE = "K7Q2XM"

_NO_AUTH = ("/pair", "/pair/confirm")


def error_body(code: str, **extra: Any) -> dict[str, Any]:
    """Build the error envelope of the contract."""
    return {
        "ok": False,
        "error": {"en": f"English text for {code}", "de": f"Deutscher Text zu {code}"},
        "code": code,
        **extra,
    }


@dataclass
class _Queued:
    status: int = 200
    json: Any = None
    text: str | None = None
    headers: dict[str, str] | None = None
    exc: BaseException | None = None


class FakeWall:
    """The server side of one device."""

    def __init__(
        self,
        aioclient_mock: AiohttpClientMocker,
        state: dict[str, Any],
        server: str = DEFAULT_SERVER,
    ) -> None:
        """Register for every request below server/api/ha/v1/."""
        self.state = state
        self.token: str | None = TOKEN
        self.code = CODE
        self.attempts_left = 5
        self.paired_device: str | None = None
        self.calls: list[tuple[str, str, Any]] = []
        self._queue: dict[str, list[_Queued]] = {}
        self._mock = aioclient_mock
        self._timer_seq = 0
        self.base = f"{server}{API_PATH}"
        self._base_path = URL(self.base).path
        pattern = re.compile("^" + re.escape(self.base) + "/")
        aioclient_mock.get(pattern, side_effect=self._handle)
        aioclient_mock.post(pattern, side_effect=self._handle)

    # Test controls

    def fail(
        self,
        path: str,
        status: int,
        code: str,
        *,
        times: int = 1,
        headers: dict[str, str] | None = None,
        **extra: Any,
    ) -> None:
        """Answer the next request(s) to path with an error envelope."""
        self._queue.setdefault(path, []).extend(
            _Queued(status=status, json=error_body(code, **extra), headers=headers)
            for _ in range(times)
        )

    def respond(
        self,
        path: str,
        *,
        status: int = 200,
        json: Any = None,
        text: str | None = None,
        headers: dict[str, str] | None = None,
        exc: BaseException | None = None,
        times: int = 1,
    ) -> None:
        """Answer the next request(s) to path with anything, or raise exc."""
        self._queue.setdefault(path, []).extend(
            _Queued(status=status, json=json, text=text, headers=headers, exc=exc)
            for _ in range(times)
        )

    def payloads(self, path: str) -> list[Any]:
        """Bodies of all requests to path, oldest first."""
        return [data for _method, p, data in self.calls if p == path]

    def count(self, path: str) -> int:
        """Number of requests to path."""
        return len(self.payloads(path))

    @property
    def last_call(self) -> tuple[str, str, Any]:
        """Method, path and body of the newest request."""
        return self.calls[-1]

    def now(self) -> int:
        """Server time in unix seconds, follows the frozen test clock."""
        return int(dt_util.utcnow().timestamp())

    def snapshot(self) -> dict[str, Any]:
        """Let timers ring or expire like the server does, return a copy."""
        now = self.now()
        self.state["time"] = now
        timers = []
        for timer in self.state["timers"]:
            if now >= timer["end"] + 900:
                continue
            timer["ringing"] = bool(timer.get("ringing")) or now >= timer["end"]
            timers.append(timer)
        timers.sort(key=lambda timer: timer["end"])
        self.state["timers"] = timers
        self.state["ringing"] = any(t["ringing"] for t in timers) or bool(
            self.state["alarm"].get("ringing")
        )
        return copy.deepcopy(self.state)

    # Request handling

    async def _handle(
        self, method: str, url: URL, data: Any
    ) -> AiohttpClientMockResponse:
        path = url.path.removeprefix(self._base_path)
        headers = self._mock.mock_calls[-1][3] or {}
        self.calls.append((method.upper(), path, copy.deepcopy(data)))
        if queue := self._queue.get(path):
            item = queue.pop(0)
            if item.exc is not None:
                raise item.exc
            return AiohttpClientMockResponse(
                method,
                url,
                status=item.status,
                json=item.json,
                text=item.text,
                headers=item.headers,
            )
        if path not in _NO_AUTH and (
            self.token is None or headers.get("Authorization") != f"Bearer {self.token}"
        ):
            status, body = 401, error_body("invalid_token")
        else:
            handler = getattr(self, "_" + path.strip("/").replace("/", "_"))
            status, body = handler(data or {})
        return AiohttpClientMockResponse(method, url, status=status, json=body)

    def _ok(self, **extra: Any) -> tuple[int, dict[str, Any]]:
        return 200, {"ok": True, **extra, "state": self.snapshot()}

    def _pair(self, data: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        self.paired_device = data.get("device")
        self.attempts_left = 5
        return 200, {"ok": True, "pairing": PAIRING, "expires_in": 300, "length": 6}

    def _pair_confirm(self, data: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if data.get("pairing") != PAIRING:
            return 404, error_body("unknown_pairing")
        if data.get("code") != self.code:
            self.attempts_left -= 1
            return 422, error_body(
                "invalid_code", attempts_left=max(0, self.attempts_left)
            )
        self.token = NEW_TOKEN
        return self._ok(token=NEW_TOKEN)

    def _state(self, data: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return self._ok()

    def _panel(self, data: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        panel = self.state["panel"]
        for key in ("on", "bright", "mode", "rotation"):
            if key in data:
                panel[key] = data[key]
        if "on" in data:
            panel["showing"] = panel["mode"] if data["on"] else "off"
        elif "mode" in data:
            panel["showing"] = data["mode"]
        return self._ok()

    def _note(self, data: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        note = self.state["note"]
        note["line1"] = str(data.get("line1", ""))[: note["max"]]
        note["line2"] = str(data.get("line2", ""))[: note["max"]]
        note["front_left"] = 600
        return self._ok()

    def _note_hide(self, data: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        self.state["note"]["front_left"] = 0
        return self._ok()

    def _timer(self, data: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if len(self.state["timers"]) >= 5:
            return 422, error_body("too_many_timers")
        self._timer_seq += 1
        seconds = int(data["seconds"])
        timer = {
            "id": f"t{self._timer_seq:07d}",
            "label": data.get("label", ""),
            "total": seconds,
            "end": self.now() + seconds,
            "ringing": False,
        }
        self.state["timers"].append(timer)
        return self._ok(timer=copy.deepcopy(timer))

    def _timer_cancel(self, data: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if timer_id := data.get("id"):
            self.state["timers"] = [
                t for t in self.state["timers"] if t["id"] != timer_id
            ]
        else:
            self.state["timers"] = []
        return self._ok()

    def _alarm(self, data: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        for key in ("on", "time", "days"):
            if key in data:
                self.state["alarm"][key] = data[key]
        return self._ok()

    def _ring_stop(self, data: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        self.state["timers"] = [t for t in self.state["timers"] if not t.get("ringing")]
        self.state["alarm"]["ringing"] = False
        return self._ok()

    def _firmware_update(self, data: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        device = self.state["device"]
        if not device.get("fw_latest") or device["fw_latest"] == device.get("fw"):
            return 409, error_body("no_update")
        device["fw_requested"] = True
        return self._ok(version=device["fw_latest"])

    def _unlink(self, data: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        self.token = None
        return 200, {"ok": True}
