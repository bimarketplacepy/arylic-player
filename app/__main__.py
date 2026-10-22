"""Arranque del servidor:  python -m app"""

from __future__ import annotations

import logging

import uvicorn

from app.config import cargar_config
from app.main import crear_app


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = cargar_config()
    uvicorn.run(crear_app(config), host=config.servidor.host, port=config.servidor.puerto)


if __name__ == "__main__":
    main()
