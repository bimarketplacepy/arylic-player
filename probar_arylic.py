"""Fase 0: diagnóstico de la conexión con el parlante Arylic (API HTTP de LinkPlay).

Uso (desde la carpeta del proyecto, con el entorno virtual activado):
    python probar_arylic.py                      # IP por defecto 10.51.85.20
    python probar_arylic.py 10.51.85.20
    python probar_arylic.py --probar-m3u http://10.51.85.12:8080/lista.m3u
    python probar_arylic.py --reproducir-url http://10.51.85.12:5901/stream/swyh.mp3

Prueba http:// y https://, muestra getStatusEx y getPlayerStatus y dice qué base usar.
Solo LEE el estado, salvo con --probar-m3u o --reproducir-url (esos cambian lo que suena).
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import sys
import time
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.arylic import MODOS_FUENTE, EstadoReproductor, decodificar_hex, ms_a_mmss
from app.biblioteca import parsear_m3u

IP_POR_DEFECTO = "10.51.85.20"

# (campo de getStatusEx, descripción, ¿viene en hexadecimal?)
CAMPOS_DISPOSITIVO: list[tuple[str, str, bool]] = [
    ("DeviceName", "Nombre", False),
    ("project", "Modelo (proyecto)", False),
    ("hardware", "Hardware", False),
    ("firmware", "Firmware", False),
    ("Release", "Fecha del firmware", False),
    ("MAC", "MAC Wi-Fi", False),
    ("apcli0", "IP por Wi-Fi", False),
    ("eth0", "IP por cable", False),
    ("essid", "Red Wi-Fi", True),
    ("RSSI", "Señal Wi-Fi (dBm)", False),
    ("internet", "Internet", False),
    ("uuid", "UUID", False),
]


def consultar(cliente: httpx.Client, base: str, comando: str) -> tuple[dict[str, Any] | None, str]:
    """Devuelve (JSON, texto). Si falla la red, (None, descripción del error)."""
    url = f"{base}/httpapi.asp?command={comando}"
    try:
        respuesta = cliente.get(url)
        respuesta.raise_for_status()
    except (httpx.HTTPError, httpx.InvalidURL) as e:
        return None, f"{type(e).__name__}: {e}"
    texto = respuesta.text.strip()
    try:
        datos = json.loads(texto)
    except ValueError:
        return None, f"respuesta no JSON: {texto[:120]!r}"
    return (datos if isinstance(datos, dict) else None), texto


def mostrar_dispositivo(datos: dict[str, Any]) -> None:
    print("\n== Dispositivo (getStatusEx) ==")
    for campo, descripcion, es_hex in CAMPOS_DISPOSITIVO:
        if campo in datos and str(datos[campo]).strip():
            valor = str(datos[campo])
            print(f"  {descripcion:<20} {decodificar_hex(valor) if es_hex else valor}")


def mostrar_estado(datos: dict[str, Any]) -> EstadoReproductor:
    estado = EstadoReproductor.desde_json(datos)
    print("\n== Reproductor (getPlayerStatus) ==")
    print(f"  Estado               {estado.status}")
    print(f"  Fuente               {MODOS_FUENTE.get(estado.modo_fuente, '?')} (mode={estado.modo_fuente})")
    print(f"  Título               {estado.titulo}")
    print(f"  Artista              {estado.artista}")
    print(f"  Álbum                {estado.album}")
    print(f"  Posición             {ms_a_mmss(estado.posicion_ms)} / {ms_a_mmss(estado.duracion_ms)}")
    print(f"  Pista de la lista    {estado.pista_actual} de {estado.total_pistas}")
    print(f"  Volumen              {estado.volumen}{' (silenciado)' if estado.silencio else ''}")
    print(f"  Modo de repetición   loopmode={estado.loop}")
    return estado


def misma_subred(ip_arylic: str, url: str) -> bool | None:
    """¿El host de la URL está en la misma /24 que el parlante? None si no son IPv4."""
    try:
        red = ipaddress.ip_network(f"{ip_arylic.split(':')[0]}/24", strict=False)
        return ipaddress.ip_address(urlsplit(url).hostname or "") in red
    except ValueError:
        return None


def revisar_lista(cliente: httpx.Client, url: str) -> int | None:
    """Antes de molestar al parlante, comprueba desde esta PC que la lista y su primera canción se descarguen.

    Devuelve la cantidad de canciones, o None si algo falla (y explica qué).
    """
    print(f"\n== Revisando la lista desde esta PC: {url} ==")
    try:
        respuesta = cliente.get(url)
        respuesta.raise_for_status()
    except httpx.HTTPError as e:
        print(f"  [FALLA] No se pudo descargar: {type(e).__name__}: {e}")
        print("  ¿Está corriendo el servidor (python -m app) en esa IP y puerto? No se envía nada al parlante.")
        return None
    pistas = parsear_m3u(respuesta.text, url)
    if not pistas:
        print("  [FALLA] La lista está vacía: poné MP3 en la carpeta de música.")
        return None
    print(f"  [OK] {len(pistas)} canciones. Primera: {pistas[0][0]}")
    try:
        cancion = cliente.get(pistas[0][1], headers={"Range": "bytes=0-1023"})
        cancion.raise_for_status()
    except httpx.HTTPError as e:
        print(f"  [FALLA] La primera canción no se descarga: {type(e).__name__}: {e}")
        return None
    print(f"  [OK] La primera canción se descarga ({cancion.headers.get('content-type', '?')})")
    return len(pistas)


def empezo_lo_nuevo(antes: EstadoReproductor | None, ahora: EstadoReproductor, pistas_esperadas: int | None) -> bool:
    """¿El parlante pasó a reproducir lo que le mandamos?

    No alcanza con status == "play": si el parlante no puede descargar la lista, responde
    "OK" igual y sigue con lo que tenía. Hay que ver un cambio respecto de antes.
    """
    if ahora.status != "play" or ahora.posicion_ms <= 0:
        return False
    if pistas_esperadas is not None and ahora.total_pistas != pistas_esperadas:
        return False
    if antes is None:
        return True
    cambio_fuente = (ahora.modo_fuente, ahora.titulo, ahora.total_pistas) != (
        antes.modo_fuente,
        antes.titulo,
        antes.total_pistas,
    )
    # Si ya sonaba lo mismo, al menos tuvo que volver a empezar.
    return cambio_fuente or ahora.posicion_ms < antes.posicion_ms


def enviar_y_seguir(
    cliente: httpx.Client,
    base: str,
    comando: str,
    segundos: int,
    antes: EstadoReproductor | None,
    pistas_esperadas: int | None = None,
) -> bool:
    """Envía un comando de reproducción y sigue el estado cada segundo. True si empezó a sonar lo nuevo."""
    print(f"\n== Enviando {comando} ==")
    url = f"{base}/httpapi.asp?command={comando}"
    try:
        respuesta = cliente.get(url)
        print(f"  Respuesta: {respuesta.status_code} {respuesta.text.strip()[:120]!r}")
    except httpx.HTTPError as e:
        print(f"  [FALLA] {type(e).__name__}: {e}")
        return False
    ahora: EstadoReproductor | None = None
    for _ in range(segundos):
        time.sleep(1)
        datos, texto = consultar(cliente, base, "getPlayerStatus")
        if datos is None:
            print(f"  ... sin respuesta ({texto})")
            continue
        ahora = EstadoReproductor.desde_json(datos)
        print(
            f"  ... {ahora.status:<6} {MODOS_FUENTE.get(ahora.modo_fuente, ahora.modo_fuente)}, "
            f"pista {ahora.pista_actual}/{ahora.total_pistas} {ms_a_mmss(ahora.posicion_ms)}  {ahora.titulo}"
        )
        if empezo_lo_nuevo(antes, ahora, pistas_esperadas):
            print("  [OK] El parlante pasó a reproducir lo nuevo.")
            return True
    print(f"  [FALLA] En {segundos} s el parlante no pasó a reproducir lo nuevo.")
    if ahora is not None and antes is not None and ahora.modo_fuente == antes.modo_fuente:
        print(
            "  Sigue con la fuente anterior: probablemente no pudo descargar desde la PC. Revisá que el servidor "
            "esté corriendo, que el firewall de Windows permita el puerto y que el parlante llegue a esa IP."
        )
    return False


def main(argv: list[str] | None = None) -> int:
    # La consola de Windows puede no soportar algunos caracteres de los títulos.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    parser = argparse.ArgumentParser(description="Diagnóstico del parlante Arylic (LinkPlay).")
    parser.add_argument("ip", nargs="?", default=IP_POR_DEFECTO, help=f"IP del Arylic (por defecto {IP_POR_DEFECTO})")
    parser.add_argument("--timeout", type=float, default=4.0, help="segundos de espera por consulta")
    parser.add_argument("--probar-m3u", metavar="URL", help="carga y reproduce esta lista M3U (cambia lo que suena)")
    parser.add_argument("--reproducir-url", metavar="URL", help="reproduce una URL suelta (por ejemplo, volver al stream de SWYH)")
    parser.add_argument("--espera", type=int, default=15, help="segundos a esperar que empiece a sonar")
    args = parser.parse_args(argv)

    print(f"Probando el Arylic en {args.ip} ...")
    base_ok: str | None = None
    info: dict[str, Any] = {}
    with httpx.Client(timeout=args.timeout, verify=False) as cliente:
        for protocolo in ("http", "https"):
            base = f"{protocolo}://{args.ip}"
            inicio = time.perf_counter()
            datos, texto = consultar(cliente, base, "getStatusEx")
            ms = (time.perf_counter() - inicio) * 1000
            if datos is not None:
                print(f"  [OK]    {base:<28} respondió en {ms:.0f} ms")
                if base_ok is None:
                    base_ok = base
                    info = datos
            else:
                print(f"  [FALLA] {base:<28} {texto}")

        if base_ok is None:
            print(
                "\nNo respondió por ninguna base. Revisá que el parlante esté encendido, que la IP sea correcta "
                "(abrí http://IP/index.html en el navegador) y que la PC esté en la misma red."
            )
            return 1

        mostrar_dispositivo(info)
        antes: EstadoReproductor | None = None
        datos, texto = consultar(cliente, base_ok, "getPlayerStatus")
        if datos is not None:
            antes = mostrar_estado(datos)
        else:
            print(f"\n[FALLA] getPlayerStatus: {texto}")

        protocolo_ok = base_ok.split(":", 1)[0]
        print(f"\n== Resultado ==\n  Base que funciona: {base_ok}")
        print(f'  En config.toml:    [arylic] ip = "{args.ip}"  protocolo = "{protocolo_ok}"')

        exito = True
        for url in (args.probar_m3u, args.reproducir_url):
            if url and misma_subred(args.ip, url) is False:
                print(
                    f"\n  Aviso: {urlsplit(url).hostname} está en otra subred que el parlante. "
                    "Funciona solo si el router deja que el parlante llegue a esa PC."
                )
        if args.probar_m3u:
            cantidad = revisar_lista(cliente, args.probar_m3u)
            if cantidad is None:
                return 2
            exito = enviar_y_seguir(
                cliente, base_ok, f"setPlayerCmd:m3u:play:{args.probar_m3u}", args.espera, antes, cantidad
            )
        if args.reproducir_url:
            exito = enviar_y_seguir(
                cliente, base_ok, f"setPlayerCmd:play:{args.reproducir_url}", args.espera, antes
            ) and exito
    return 0 if exito else 2


if __name__ == "__main__":
    sys.exit(main())
