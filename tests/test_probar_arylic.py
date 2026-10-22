"""La Fase 0 no puede dar "OK" si el parlante sigue con lo que ya sonaba."""

from app.arylic import EstadoReproductor
from probar_arylic import empezo_lo_nuevo, misma_subred


def _estado(modo: int, titulo: str, total: int, pos: int, status: str = "play") -> EstadoReproductor:
    return EstadoReproductor(
        status=status, volumen=68, silencio=False, posicion_ms=pos, duracion_ms=223_000,
        titulo=titulo, artista="", album="", pista_actual=1, total_pistas=total, loop=4, modo_fuente=modo,
    )


# Lo que se vio en el local: SWYH por DLNA, 1 de 1, y el parlante nunca cambió.
SWYH = _estado(2, "Funky Sunrise (1)", 1, 6_000)


def test_sigue_con_lo_anterior_no_es_exito() -> None:
    assert not empezo_lo_nuevo(SWYH, _estado(2, "Funky Sunrise (1)", 1, 8_000), pistas_esperadas=1)
    assert not empezo_lo_nuevo(SWYH, _estado(2, "Funky Sunrise (1)", 1, 8_000), pistas_esperadas=None)


def test_paso_a_la_lista() -> None:
    assert empezo_lo_nuevo(SWYH, _estado(10, "Ola de verano", 12, 1_500), pistas_esperadas=12)


def test_lista_con_otra_cantidad_no_es_la_nuestra() -> None:
    assert not empezo_lo_nuevo(SWYH, _estado(10, "Ola de verano", 3, 1_500), pistas_esperadas=12)


def test_cargando_todavia_no() -> None:
    assert not empezo_lo_nuevo(SWYH, _estado(10, "", 12, 0, status="load"), pistas_esperadas=12)


def test_relanzar_la_misma_lista_exige_que_vuelva_a_empezar() -> None:
    antes = _estado(10, "Ola de verano", 12, 90_000)
    assert not empezo_lo_nuevo(antes, _estado(10, "Ola de verano", 12, 92_000), pistas_esperadas=12)
    assert empezo_lo_nuevo(antes, _estado(10, "Ola de verano", 12, 1_000), pistas_esperadas=12)


def test_misma_subred() -> None:
    assert misma_subred("10.51.85.20", "http://10.51.85.12:8080/lista.m3u") is True
    assert misma_subred("10.51.85.20", "http://10.51.80.21:8080/lista.m3u") is False
    assert misma_subred("10.51.85.20", "http://pc-local:8080/lista.m3u") is None
