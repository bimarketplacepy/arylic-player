"""Simulador mínimo de un parlante Arylic (API HTTP de LinkPlay) para probar sin hardware.

Uso:
    python -m simulador.arylic_falso --puerto 8099
y en config.toml:
    [arylic]
    ip = "127.0.0.1:8099"
    protocolo = "http"

Responde a getStatusEx, getPlayerStatus, GetTrackNumber y a los setPlayerCmd que usa el
servidor. Al recibir m3u:play descarga la lista de verdad (así valida las URLs) y simula
el avance del tiempo: cada pista dura DURACION_PISTA_MS y al terminar pasa a la siguiente
según el loopmode, igual que el parlante.
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

from app.biblioteca import parsear_m3u

log = logging.getLogger(__name__)

DURACION_PISTA_MS = 180_000


def a_hex(texto: str) -> str:
    """Igual que el parlante: texto UTF-8 en hexadecimal en mayúsculas."""
    return texto.encode("utf-8").hex().upper()


@dataclass
class EstadoSimulado:
    status: str = "none"
    vol: int = 74
    mute: int = 0
    loop: int = 4
    pistas: list[tuple[str, str]] = field(default_factory=list)
    indice: int = 0  # desde 0
    reloj: Callable[[], float] = time.monotonic
    _inicio: float = 0.0  # instante (según reloj) en que "empezó" la pista actual
    _pos_pausa: int = 0

    def posicion_ms(self) -> int:
        if self.status == "play":
            return int((self.reloj() - self._inicio) * 1000)
        if self.status == "pause":
            return self._pos_pausa
        return 0

    def empezar(self, indice: int) -> None:
        self.indice = indice
        self.status = "play"
        self._inicio = self.reloj()

    def pausar(self) -> None:
        if self.status == "play":
            self._pos_pausa = self.posicion_ms()
            self.status = "pause"

    def reanudar(self) -> None:
        if self.status == "pause":
            self._inicio = self.reloj() - self._pos_pausa / 1000
            self.status = "play"

    def proximo_indice(self, automatico: bool) -> int | None:
        """Pista que sigue. None = fin de la lista sin repetición (el parlante queda en stop)."""
        cantidad = len(self.pistas)
        if automatico and self.loop == 1:
            return self.indice
        if self.loop in (2, 3):
            return random.randrange(cantidad)
        if self.indice + 1 < cantidad:
            return self.indice + 1
        return None if (automatico and self.loop == 4) else 0

    def actualizar(self) -> None:
        """Avanza las pistas que ya terminaron según el tiempo transcurrido."""
        while self.status == "play" and self.pistas and self.posicion_ms() >= DURACION_PISTA_MS:
            fin = self._inicio + DURACION_PISTA_MS / 1000
            siguiente = self.proximo_indice(automatico=True)
            if siguiente is None:
                self.status = "stop"
                return
            self.indice = siguiente
            self._inicio = fin

    def player_status(self) -> dict[str, str]:
        """Respuesta con el mismo formato que getPlayerStatus del parlante real."""
        self.actualizar()
        hay_pista = bool(self.pistas) and self.status in ("play", "pause")
        titulo = self.pistas[self.indice][0] if hay_pista else ""
        return {
            "type": "0",
            "ch": "0",
            "mode": "10" if self.pistas else "0",
            "loop": str(self.loop),
            "eq": "0",
            "status": self.status,
            "curpos": str(self.posicion_ms()),
            "offset_pts": "0",
            "totlen": str(DURACION_PISTA_MS if hay_pista else 0),
            "Title": a_hex(titulo),
            "Artist": a_hex("Simulador" if hay_pista else ""),
            "Album": a_hex("Not Specified"),
            "alarmflag": "0",
            "plicount": str(len(self.pistas)),
            "plicurr": str(self.indice + 1 if self.pistas else 0),
            "vol": str(self.vol),
            "mute": str(self.mute),
        }


STATUS_EX = {
    "DeviceName": "Arylic simulado",
    "project": "SIMULADOR",
    "hardware": "sim",
    "firmware": "0.0.0-sim",
    "Release": "20260101",
    "MAC": "00:00:00:00:00:00",
    "apcli0": "127.0.0.1",
    "essid": a_hex("Red del local"),
    "RSSI": "-50",
    "internet": "1",
    "uuid": "SIMULADOR-0000",
}


def crear_simulador(reloj: Callable[[], float] = time.monotonic) -> FastAPI:
    """Crea el simulador. En tests, app.state.transporte_descarga conecta la descarga de la
    lista con el servidor en memoria (sin red)."""
    app = FastAPI(title="Arylic simulado")
    sim = EstadoSimulado(reloj=reloj)
    app.state.sim = sim
    app.state.transporte_descarga = None

    async def cargar_lista(url: str) -> None:
        sim.status = "load"
        try:
            async with httpx.AsyncClient(transport=app.state.transporte_descarga, timeout=10) as cliente:
                respuesta = await cliente.get(url)
                respuesta.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("No se pudo descargar la lista %s: %r", url, e)
            sim.status = "stop"
            return
        sim.pistas = parsear_m3u(respuesta.text, url)
        if sim.pistas:
            sim.empezar(0)
        else:
            sim.status = "stop"

    async def jugador(sub: str) -> str:
        nombre, _, argumento = sub.partition(":")
        if sub.startswith("m3u:play:"):
            await cargar_lista(sub.removeprefix("m3u:play:"))
        elif nombre == "play" and argumento:
            sim.pistas = [(argumento.rsplit("/", 1)[-1], argumento)]
            sim.empezar(0)
        elif nombre == "pause":
            sim.pausar()
        elif nombre == "resume":
            sim.reanudar()
        elif nombre == "onepause":
            if sim.status == "pause":
                sim.reanudar()
            else:
                sim.pausar()
        elif nombre == "stop":
            sim.status = "stop"
        elif nombre in ("next", "prev") and sim.pistas:
            if nombre == "next":
                indice = sim.proximo_indice(automatico=False) or 0
            else:
                indice = (sim.indice - 1) % len(sim.pistas)
            sim.empezar(indice)
        elif nombre == "playindex" and argumento.isdigit() and 1 <= int(argumento) <= len(sim.pistas):
            sim.empezar(int(argumento) - 1)
        elif nombre == "vol" and argumento.isdigit():
            sim.vol = min(100, int(argumento))
        elif nombre == "mute" and argumento in ("0", "1"):
            sim.mute = int(argumento)
        elif nombre == "loopmode" and argumento in ("0", "1", "2", "3", "4"):
            sim.loop = int(argumento)
        else:
            return "unknown command"
        return "OK"

    @app.get("/httpapi.asp")
    async def httpapi(request: Request) -> PlainTextResponse:
        comando = request.query_params.get("command", "")
        if comando == "getStatusEx":
            texto = json.dumps(STATUS_EX)
        elif comando == "getPlayerStatus":
            texto = json.dumps(sim.player_status())
        elif comando == "GetTrackNumber":
            sim.actualizar()
            texto = str(sim.indice + 1 if sim.pistas else 0)
        elif comando.startswith("setPlayerCmd:"):
            texto = await jugador(comando.removeprefix("setPlayerCmd:"))
        else:
            texto = "unknown command"
        log.info("%s → %s", comando, texto[:80])
        return PlainTextResponse(texto)

    return app


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description="Simulador de parlante Arylic")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--puerto", type=int, default=8099)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s SIMULADOR %(message)s")
    uvicorn.run(crear_simulador(), host=args.host, port=args.puerto, log_level="warning")


if __name__ == "__main__":
    main()
