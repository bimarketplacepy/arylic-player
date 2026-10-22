"""Carga y validación de la configuración (config.toml)."""

from __future__ import annotations

import logging
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

RAIZ_PROYECTO = Path(__file__).resolve().parent.parent
TOKEN_POR_DEFECTO = "cambiar-este-token"

# Modo de reproducción → valor de setPlayerCmd:loopmode (ambos repiten la lista al terminar).
MODOS: dict[str, int] = {"secuencial": 0, "aleatorio": 2}
PROTOCOLOS = ("auto", "http", "https")


class ErrorConfig(ValueError):
    """Valor inválido en config.toml."""


@dataclass(frozen=True)
class ConfigArylic:
    ip: str = "10.51.85.20"
    protocolo: str = "auto"
    timeout: float = 5.0


@dataclass(frozen=True)
class ConfigServidor:
    ip_pc: str = "10.51.85.12"
    puerto: int = 8080
    host: str = "0.0.0.0"
    carpeta_musica: Path = RAIZ_PROYECTO / "musica"
    token: str = TOKEN_POR_DEFECTO

    @property
    def url_base(self) -> str:
        """URL con la que el parlante llega a esta PC (para armar la lista M3U)."""
        return f"http://{self.ip_pc}:{self.puerto}"


@dataclass(frozen=True)
class ConfigReproduccion:
    volumen_inicial: int = 40
    modo: str = "secuencial"

    @property
    def loopmode(self) -> int:
        return MODOS[self.modo]


@dataclass(frozen=True)
class Config:
    arylic: ConfigArylic = field(default_factory=ConfigArylic)
    servidor: ConfigServidor = field(default_factory=ConfigServidor)
    reproduccion: ConfigReproduccion = field(default_factory=ConfigReproduccion)


def cargar_config(ruta: Path | None = None) -> Config:
    """Lee config.toml (o la ruta de la variable ARYLIC_CONFIG). Si no existe, usa los valores por defecto."""
    if ruta is None:
        ruta = Path(os.environ.get("ARYLIC_CONFIG", RAIZ_PROYECTO / "config.toml"))
    datos: dict[str, Any] = {}
    if ruta.exists():
        # utf-8-sig: algunos editores de Windows agregan un BOM al principio y tomllib no lo acepta.
        try:
            datos = tomllib.loads(ruta.read_text(encoding="utf-8-sig"))
        except tomllib.TOMLDecodeError as e:
            raise ErrorConfig(f"{ruta} tiene un error de formato: {e}") from e
        log.info("Configuración cargada de %s", ruta)
    else:
        log.warning("No existe %s: se usan los valores por defecto", ruta)
    return config_desde_dict(datos, base=ruta.parent)


def config_desde_dict(datos: dict[str, Any], base: Path = RAIZ_PROYECTO) -> Config:
    """Arma y valida la configuración. Las rutas relativas se resuelven desde `base`."""
    a = datos.get("arylic", {})
    s = datos.get("servidor", {})
    r = datos.get("reproduccion", {})

    try:
        arylic = ConfigArylic(
            ip=str(a.get("ip", ConfigArylic.ip)).strip(),
            protocolo=str(a.get("protocolo", ConfigArylic.protocolo)).strip().lower(),
            timeout=float(a.get("timeout", ConfigArylic.timeout)),
        )
        carpeta = Path(s.get("carpeta_musica", "musica"))
        if not carpeta.is_absolute():
            carpeta = base / carpeta
        servidor = ConfigServidor(
            ip_pc=str(s.get("ip_pc", ConfigServidor.ip_pc)).strip(),
            puerto=int(s.get("puerto", ConfigServidor.puerto)),
            host=str(s.get("host", ConfigServidor.host)).strip(),
            carpeta_musica=carpeta.resolve(),
            token=str(s.get("token", ConfigServidor.token)),
        )
        reproduccion = ConfigReproduccion(
            volumen_inicial=int(r.get("volumen_inicial", ConfigReproduccion.volumen_inicial)),
            modo=str(r.get("modo", ConfigReproduccion.modo)).strip().lower(),
        )
    except (TypeError, ValueError) as e:
        raise ErrorConfig(f"Valor con formato inválido en la configuración: {e}") from e

    if not arylic.ip:
        raise ErrorConfig("[arylic] ip no puede estar vacío")
    if arylic.protocolo not in PROTOCOLOS:
        raise ErrorConfig(f"[arylic] protocolo debe ser uno de {PROTOCOLOS}")
    if arylic.timeout <= 0:
        raise ErrorConfig("[arylic] timeout debe ser mayor que 0")
    if not 1 <= servidor.puerto <= 65535:
        raise ErrorConfig("[servidor] puerto debe estar entre 1 y 65535")
    if not servidor.token.strip():
        raise ErrorConfig("[servidor] token no puede estar vacío")
    if not 0 <= reproduccion.volumen_inicial <= 100:
        raise ErrorConfig("[reproduccion] volumen_inicial debe estar entre 0 y 100")
    if reproduccion.modo not in MODOS:
        raise ErrorConfig(f"[reproduccion] modo debe ser uno de {tuple(MODOS)}")

    return Config(arylic=arylic, servidor=servidor, reproduccion=reproduccion)
