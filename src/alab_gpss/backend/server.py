"""Server script to run the FastAPI application."""

from pathlib import Path

import uvicorn
from alab_management.device_view.device import mock

from alab_gpss.backend.app import app

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        ssl_keyfile=mock(return_constant=None)(lambda: Path(".") / "ssl_keys" / "aragorn-key.pem")(),
        ssl_certfile=mock(return_constant=None)(lambda: Path(".") / "ssl_keys" / "aragorn-cert.pem")(),
        timeout_graceful_shutdown=1,
    )
