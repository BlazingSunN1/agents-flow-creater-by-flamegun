from __future__ import annotations

import functools
import http.server
import threading
from pathlib import Path


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


class ProjectHttpServer:
    def __init__(self, root: Path) -> None:
        handler = functools.partial(QuietHandler, directory=str(root))
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(
            target=lambda: self.server.serve_forever(poll_interval=0.01), daemon=True,
        )
        self.thread.start()

    def url(self, relative: str) -> str:
        return f"http://127.0.0.1:{self.server.server_port}/{relative.lstrip('/')}"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
