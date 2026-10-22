"""Armado de la aplicación FastAPI."""

from __future__ import annotations

import logging
import mimetypes
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.arylic import ArylicNoDisponible, ClienteArylic, ErrorArylic
from app.config import TOKEN_POR_DEFECTO, Config, cargar_config
from app.rutas import control, publico

log = logging.getLogger(__name__)

# En Windows el tipo MIME sale del registro y puede venir mal; el parlante necesita audio/mpeg.
mimetypes.add_type("audio/mpeg", ".mp3")


def crear_app(config: Config | None = None, cliente: ClienteArylic | None = None) -> FastAPI:
    """Crea la app. Los tests pasan su propia config y un cliente conectado al simulador."""
    config = config or cargar_config()
    config.servidor.carpeta_musica.mkdir(parents=True, exist_ok=True)
    cliente_propio = cliente is None
    cliente = cliente or ClienteArylic(config.arylic.ip, config.arylic.protocolo, config.arylic.timeout)

    @asynccontextmanager
    async def ciclo_de_vida(app: FastAPI) -> AsyncIterator[None]:
        if config.servidor.token == TOKEN_POR_DEFECTO:
            log.warning("El token sigue siendo el de ejemplo: cambialo en config.toml")
        log.info(
            "Música en %s, lista en %s/lista.m3u, parlante %s",
            config.servidor.carpeta_musica,
            config.servidor.url_base,
            config.arylic.ip,
        )
        yield
        if cliente_propio:
            await cliente.cerrar()

    app = FastAPI(title="Reproductor Arylic", lifespan=ciclo_de_vida)
    app.state.config = config
    app.state.arylic = cliente

    app.include_router(publico.router)
    app.include_router(control.router)
    app.mount("/musica", StaticFiles(directory=config.servidor.carpeta_musica), name="musica")

    @app.exception_handler(ErrorArylic)
    async def parlante_con_error(request: Request, exc: ErrorArylic) -> JSONResponse:
        # Un parlante caído es algo esperable: se informa al panel sin tumbar nada.
        log.warning("%s %s: %s", request.method, request.url.path, exc)
        codigo = 503 if isinstance(exc, ArylicNoDisponible) else 502
        return JSONResponse(status_code=codigo, content={"conectado": False, "error": str(exc)})

    return app
