"""Cliente de la API HTTP de LinkPlay que usan los parlantes Arylic.

Todos los comandos van por GET a  BASE/httpapi.asp?command=COMANDO.
Cualquier falla de red se convierte en ArylicNoDisponible, para que quien llama
decida qué hacer sin que una excepción de httpx tumbe el servidor.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict, dataclass
from typing import Any

import httpx

log = logging.getLogger(__name__)

# Campo "mode" de getPlayerStatus: de dónde viene el audio (solo los valores más comunes).
MODOS_FUENTE: dict[int, str] = {
    0: "ninguna",
    1: "AirPlay",
    2: "DLNA",
    10: "red (URL / lista)",
    11: "USB",
    31: "Spotify Connect",
    40: "entrada auxiliar",
    41: "Bluetooth",
    43: "óptica",
    99: "esclavo multiroom",
}


class ErrorArylic(Exception):
    """Error base al hablar con el parlante."""


class ArylicNoDisponible(ErrorArylic):
    """El parlante no respondió (apagado, sin red, IP equivocada o timeout)."""


class RespuestaInvalida(ErrorArylic):
    """El parlante respondió algo que no se pudo interpretar."""


def decodificar_hex(valor: str | None) -> str:
    """Title/Artist/Album llegan como texto UTF-8 en hexadecimal. Si no es hex, se devuelve tal cual."""
    if not valor:
        return ""
    try:
        return bytes.fromhex(valor).decode("utf-8", errors="replace")
    except ValueError:
        return valor


def ms_a_mmss(ms: int) -> str:
    """Milisegundos → "mm:ss" (los minutos pueden pasar de 59)."""
    segundos = max(0, ms) // 1000
    return f"{segundos // 60:02d}:{segundos % 60:02d}"


def _entero(valor: Any, defecto: int = 0) -> int:
    """La API devuelve todos los números como strings; tolera valores vacíos o raros."""
    try:
        return int(valor)
    except (TypeError, ValueError):
        return defecto


@dataclass(frozen=True)
class EstadoReproductor:
    """Respuesta de getPlayerStatus ya convertida a tipos de Python."""

    status: str  # play, pause, stop, load o none
    volumen: int
    silencio: bool
    posicion_ms: int
    duracion_ms: int
    titulo: str
    artista: str
    album: str
    pista_actual: int  # plicurr (desde 1)
    total_pistas: int  # plicount
    loop: int
    modo_fuente: int

    @classmethod
    def desde_json(cls, datos: dict[str, Any]) -> EstadoReproductor:
        return cls(
            status=str(datos.get("status", "")).lower(),
            volumen=_entero(datos.get("vol")),
            silencio=_entero(datos.get("mute")) == 1,
            posicion_ms=_entero(datos.get("curpos")),
            duracion_ms=_entero(datos.get("totlen")),
            titulo=decodificar_hex(datos.get("Title")),
            artista=decodificar_hex(datos.get("Artist")),
            album=decodificar_hex(datos.get("Album")),
            pista_actual=_entero(datos.get("plicurr")),
            total_pistas=_entero(datos.get("plicount")),
            loop=_entero(datos.get("loop")),
            modo_fuente=_entero(datos.get("mode")),
        )

    def a_dict(self) -> dict[str, Any]:
        """Versión para la API/panel, con tiempos en mm:ss y nombre de la fuente."""
        datos = asdict(self)
        datos["posicion"] = ms_a_mmss(self.posicion_ms)
        datos["duracion"] = ms_a_mmss(self.duracion_ms)
        datos["fuente"] = MODOS_FUENTE.get(self.modo_fuente, f"modo {self.modo_fuente}")
        return datos


class ClienteArylic:
    """Habla con un parlante Arylic. Usar una sola instancia por parlante."""

    def __init__(
        self,
        ip: str,
        protocolo: str = "auto",
        timeout: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.ip = ip
        self.protocolo = protocolo
        # Con "auto" la base se detecta en el primer comando y se olvida si deja de responder.
        self._base: str | None = None if protocolo == "auto" else f"{protocolo}://{ip}"
        # verify=False: con https el parlante usa un certificado autofirmado.
        self._http = httpx.AsyncClient(timeout=timeout, verify=False, transport=transport)
        # El servidor web del parlante es chico: mandamos un comando a la vez.
        self._candado = asyncio.Lock()

    @property
    def base(self) -> str | None:
        return self._base

    async def cerrar(self) -> None:
        await self._http.aclose()

    @staticmethod
    def _url(base: str, comando: str) -> str:
        # El comando va sin codificar: el firmware espera los ":" y "/" tal cual.
        return f"{base}/httpapi.asp?command={comando}"

    async def detectar_base(self) -> str:
        """Prueba http y luego https con getStatusEx y recuerda la primera que responde JSON."""
        errores: list[str] = []
        for protocolo in ("http", "https"):
            base = f"{protocolo}://{self.ip}"
            try:
                respuesta = await self._http.get(self._url(base, "getStatusEx"))
                respuesta.raise_for_status()
                json.loads(respuesta.text)
            except (httpx.HTTPError, httpx.InvalidURL, ValueError) as e:
                errores.append(f"{protocolo}: {e!r}")
                continue
            if self._base != base:
                log.info("Arylic responde en %s", base)
            self._base = base
            return base
        raise ArylicNoDisponible(f"El Arylic {self.ip} no responde ({'; '.join(errores)})")

    async def comando(self, comando: str) -> str:
        """Envía un comando y devuelve la respuesta como texto."""
        async with self._candado:
            base = self._base or await self.detectar_base()
            try:
                respuesta = await self._http.get(self._url(base, comando))
                respuesta.raise_for_status()
            except (httpx.HTTPError, httpx.InvalidURL) as e:
                if self.protocolo == "auto":
                    self._base = None  # la próxima vez vuelve a detectar
                raise ArylicNoDisponible(f"El Arylic no respondió a {comando!r}: {e!r}") from e
            texto = respuesta.text.strip()
            log.debug("Arylic %s → %s", comando, texto[:200])
            return texto

    async def comando_json(self, comando: str) -> dict[str, Any]:
        texto = await self.comando(comando)
        try:
            datos = json.loads(texto)
        except ValueError as e:
            raise RespuestaInvalida(f"Respuesta no JSON a {comando!r}: {texto[:100]!r}") from e
        if not isinstance(datos, dict):
            raise RespuestaInvalida(f"Respuesta inesperada a {comando!r}: {texto[:100]!r}")
        return datos

    async def _jugador(self, subcomando: str) -> str:
        """setPlayerCmd:<subcomando>. El firmware contesta "OK"; si no, solo se avisa en el log."""
        texto = await self.comando(f"setPlayerCmd:{subcomando}")
        if texto.upper() != "OK":
            log.warning("Arylic respondió %r a setPlayerCmd:%s", texto[:100], subcomando)
        return texto

    # --- Consultas ---

    async def info_dispositivo(self) -> dict[str, Any]:
        return await self.comando_json("getStatusEx")

    async def estado(self) -> EstadoReproductor:
        return EstadoReproductor.desde_json(await self.comando_json("getPlayerStatus"))

    # --- Reproducción ---

    async def reproducir_lista(self, url_m3u: str) -> None:
        """Carga una lista M3U por URL y empieza por la primera pista."""
        await self._jugador(f"m3u:play:{url_m3u}")

    async def reproducir_url(self, url: str) -> None:
        await self._jugador(f"play:{url}")

    async def reproducir_indice(self, numero: int) -> None:
        """Pista N de la lista cargada (desde 1)."""
        if numero < 1:
            raise ValueError("La pista empieza en 1")
        await self._jugador(f"playindex:{numero}")

    async def pausa(self) -> None:
        await self._jugador("pause")

    async def reanudar(self) -> None:
        await self._jugador("resume")

    async def siguiente(self) -> None:
        await self._jugador("next")

    async def anterior(self) -> None:
        await self._jugador("prev")

    async def volumen(self, valor: int) -> None:
        if not 0 <= valor <= 100:
            raise ValueError("El volumen va de 0 a 100")
        await self._jugador(f"vol:{valor}")

    async def silencio(self, activado: bool) -> None:
        await self._jugador(f"mute:{int(activado)}")

    async def modo_bucle(self, modo: int) -> None:
        """0 secuencial+repite, 1 una+repite, 2 aleatorio+repite, 3 aleatorio, 4 secuencial sin repetir."""
        if not 0 <= modo <= 4:
            raise ValueError("loopmode va de 0 a 4")
        await self._jugador(f"loopmode:{modo}")
