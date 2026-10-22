"""Lectura de la carpeta de música y armado de la lista M3U."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from urllib.parse import quote, urljoin

EXTENSIONES = {".mp3"}


def listar_canciones(carpeta: Path) -> list[str]:
    """Nombres de los MP3 de la carpeta (sin subcarpetas ni ocultos), ordenados por nombre."""
    if not carpeta.is_dir():
        return []
    nombres = [
        p.name
        for p in carpeta.iterdir()
        if p.is_file() and p.suffix.lower() in EXTENSIONES and not p.name.startswith(".")
    ]
    # casefold: "b" y "B" ordenan juntas; el segundo criterio deja el orden estable.
    return sorted(nombres, key=lambda n: (n.casefold(), n))


def titulo(nombre: str) -> str:
    """Título a mostrar: el nombre del archivo sin la extensión."""
    return Path(nombre).stem


def url_cancion(url_base: str, nombre: str) -> str:
    """URL absoluta del MP3. Espacios, ñ, tildes, #, & y demás quedan codificados (%XX)."""
    return f"{url_base}/musica/{quote(nombre, safe='')}"


def generar_m3u(nombres: Iterable[str], url_base: str) -> str:
    """Lista M3U extendida: #EXTM3U y, por canción, #EXTINF:-1,TITULO + URL absoluta."""
    lineas = ["#EXTM3U"]
    for nombre in nombres:
        lineas.append(f"#EXTINF:-1,{titulo(nombre)}")
        lineas.append(url_cancion(url_base, nombre))
    return "\n".join(lineas) + "\n"


def parsear_m3u(texto: str, url_lista: str) -> list[tuple[str, str]]:
    """Lee una lista M3U y devuelve [(título, url absoluta)]. Las URL relativas se resuelven contra url_lista."""
    pistas: list[tuple[str, str]] = []
    titulo_pendiente = ""
    for linea in texto.splitlines():
        linea = linea.strip()
        if not linea:
            continue
        if linea.startswith("#EXTINF:"):
            titulo_pendiente = linea.split(",", 1)[1] if "," in linea else ""
        elif not linea.startswith("#"):
            url = urljoin(url_lista, linea)
            pistas.append((titulo_pendiente or url.rsplit("/", 1)[-1], url))
            titulo_pendiente = ""
    return pistas
