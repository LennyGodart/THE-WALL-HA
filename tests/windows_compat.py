"""Let the Home Assistant test harness start on Windows.

tests/conftest.py imports this module first and only then loads the
pytest-homeassistant-custom-component plugin, whose entry point is blocked in
pyproject.toml for that reason. On any other system it does nothing. Home
Assistant itself does not run on Windows; this only makes the tests run there.

1. homeassistant.runner imports fcntl and homeassistant.util.resource imports
   resource. Neither exists on Windows. The tests never use them, so empty
   stand-ins are enough.
2. The plugin blocks every non-Unix socket with pytest-socket. The asyncio
   event loop on Windows builds its internal wake-up pipe with
   socket.socketpair(), which Windows emulates with two TCP sockets on
   127.0.0.1. That pair is created with the real socket class; all other
   sockets stay blocked.
"""

from __future__ import annotations

import socket
import sys
import types
from typing import Any

if sys.platform == "win32":
    if "fcntl" not in sys.modules:
        fcntl = types.ModuleType("fcntl")
        fcntl.LOCK_SH = 1  # type: ignore[attr-defined]
        fcntl.LOCK_EX = 2  # type: ignore[attr-defined]
        fcntl.LOCK_NB = 4  # type: ignore[attr-defined]
        fcntl.LOCK_UN = 8  # type: ignore[attr-defined]
        fcntl.flock = lambda *_args, **_kwargs: None  # type: ignore[attr-defined]
        sys.modules["fcntl"] = fcntl

    if "resource" not in sys.modules:
        resource = types.ModuleType("resource")
        resource.RLIMIT_NOFILE = 7  # type: ignore[attr-defined]
        resource.getrlimit = lambda _which: (8192, 8192)  # type: ignore[attr-defined]
        resource.setrlimit = lambda _which, _limits: None  # type: ignore[attr-defined]
        sys.modules["resource"] = resource

    _real_socket = socket.socket
    _real_socketpair = socket.socketpair

    def _socketpair(*args: Any, **kwargs: Any) -> tuple[socket.socket, socket.socket]:
        guarded = socket.socket
        socket.socket = _real_socket  # type: ignore[misc]
        try:
            return _real_socketpair(*args, **kwargs)
        finally:
            socket.socket = guarded  # type: ignore[misc]

    socket.socketpair = _socketpair
