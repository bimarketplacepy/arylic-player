"""Acciones de alto nivel sobre el parlante (las usan la API y, más adelante, el vigilante)."""

from __future__ import annotations

import logging

from app.arylic import ClienteArylic
from app.biblioteca import listar_canciones
from app.config import Config

log = logging.getLogger(__name__)


class SinCanciones(Exception):
    """La carpeta de música no tiene MP3."""


def url_lista(config: Config) -> str:
    return f"{config.servidor.url_base}/lista.m3u"


async def iniciar_album(cliente: ClienteArylic, config: Config, volumen: int | None = None) -> int:
    """Carga la lista completa en el parlante, fija el modo de repetición y devuelve cuántas canciones hay.

    El loopmode se fija DESPUÉS de cargar la lista porque algunos firmwares lo reinician
    al cambiar de lista. Con 0 (secuencial) o 2 (aleatorio) la lista se repite y no se detiene.
    """
    canciones = listar_canciones(config.servidor.carpeta_musica)
    if not canciones:
        raise SinCanciones(f"No hay MP3 en {config.servidor.carpeta_musica}")
    await cliente.reproducir_lista(url_lista(config))
    await cliente.modo_bucle(config.reproduccion.loopmode)
    if volumen is not None:
        await cliente.volumen(volumen)
    log.info(
        "Álbum iniciado: %d canciones, modo %s%s",
        len(canciones),
        config.reproduccion.modo,
        f", volumen {volumen}" if volumen is not None else "",
    )
    return len(canciones)
