"""El simulador tiene que comportarse como el parlante, porque el vigilante (Fase 3) se prueba contra él."""

from simulador.arylic_falso import DURACION_PISTA_MS, EstadoSimulado

PISTAS = [("uno", "u1"), ("dos", "u2"), ("tres", "u3")]


class Reloj:
    def __init__(self) -> None:
        self.ahora = 1000.0

    def __call__(self) -> float:
        return self.ahora

    def avanzar_ms(self, ms: int) -> None:
        self.ahora += ms / 1000


def _sim(loop: int) -> tuple[EstadoSimulado, Reloj]:
    reloj = Reloj()
    sim = EstadoSimulado(reloj=reloj, loop=loop, pistas=list(PISTAS))
    sim.empezar(0)
    return sim, reloj


def test_secuencial_con_repeticion_vuelve_al_principio() -> None:
    sim, reloj = _sim(loop=0)
    reloj.avanzar_ms(3 * DURACION_PISTA_MS + 5_000)
    estado = sim.player_status()
    assert (estado["status"], estado["plicurr"], estado["curpos"]) == ("play", "1", "5000")


def test_sin_repeticion_se_detiene_al_final() -> None:
    sim, reloj = _sim(loop=4)
    reloj.avanzar_ms(3 * DURACION_PISTA_MS + 1)
    assert sim.player_status()["status"] == "stop"


def test_pausa_congela_la_posicion() -> None:
    sim, reloj = _sim(loop=0)
    reloj.avanzar_ms(10_000)
    sim.pausar()
    reloj.avanzar_ms(60_000)
    assert sim.player_status()["curpos"] == "10000"
    sim.reanudar()
    reloj.avanzar_ms(1_000)
    assert sim.player_status()["curpos"] == "11000"
