from __future__ import annotations

import errno
import socket
import sys
from collections.abc import Iterator
from contextlib import contextmanager


class LocalServerError(RuntimeError):
    """The local server could not reserve its configured address."""


@contextmanager
def local_listener(host: str, port: int) -> Iterator[socket.socket]:
    """Reserve the address before touching data and retain it through server startup.

    Settings permits only localhost and IPv4 loopback addresses. Resolving localhost
    to IPv4 here also keeps the printed address usable when a machine prefers IPv6.
    """

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        if sys.platform == "win32":
            # SO_REUSEADDR on Windows can let another process share a live port.
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            # Permit a clean restart while old connections finish TIME_WAIT.
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind(("127.0.0.1" if host == "localhost" else host, port))
            listener.listen(128)
        except OSError as exc:
            if exc.errno in {errno.EADDRINUSE, 10048}:
                raise LocalServerError(
                    f"Port {port} is already in use. Stop your other Incoooming window with "
                    "Ctrl+C, or choose another SCHWAB_DASHBOARD_PORT in .env. "
                    "Nothing was stopped and no database was changed."
                ) from exc
            raise LocalServerError(
                f"Could not open the local address {host}:{port}. Check the address and "
                "your computer's network permissions. Nothing was stopped and no database "
                "was changed."
            ) from exc
        yield listener
