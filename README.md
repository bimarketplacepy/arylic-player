# Reproductor remoto para parlantes Arylic

Reemplaza el streaming en vivo ("Stream What You Hear") por un sistema más robusto:
la PC del local sirve los MP3 y una lista `.m3u` por HTTP, y le ordena al parlante Arylic
(plataforma LinkPlay) que la reproduzca. El parlante descarga cada canción completa y la
bufferiza, así los microcortes de red no se escuchan.

Estado: **Fases 0 y 1** (diagnóstico, servidor y control básico). Próximas: panel web,
vigilante con horario, subida de canciones e instalación como servicio de Windows.

## Requisitos

- Windows con Python 3.11 o superior (probado con 3.14).
- Un parlante Arylic / LinkPlay en la misma red que la PC.

## Instalación

```bat
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy config.example.toml config.toml
```

Editá `config.toml`: IP del parlante, IP de la PC, carpeta de música y un token propio.
Abrí el puerto en el firewall (terminal como administrador):

```bat
netsh advfirewall firewall add rule name="Reproductor Arylic" dir=in action=allow protocol=TCP localport=8080
```

## Uso

Diagnóstico del parlante (solo lee el estado):

```bat
.venv\Scripts\python probar_arylic.py 10.51.85.20
```

Servidor:

```bat
.venv\Scripts\python -m app
```

Probar la lista en el parlante (cambia lo que suena):

```bat
.venv\Scripts\python probar_arylic.py --probar-m3u http://IP_DE_LA_PC:8080/lista.m3u
```

## API

Sin token (los pide el parlante): `GET /lista.m3u`, `GET /musica/<archivo>`, `GET /salud`.

Con header `X-Token`:

| Método | Ruta | Cuerpo |
|---|---|---|
| GET | `/api/estado` | |
| POST | `/api/album/iniciar` | `{"volumen": 40}` (opcional) |
| POST | `/api/pausa`, `/api/reanudar`, `/api/siguiente`, `/api/anterior` | |
| POST | `/api/volumen` | `{"valor": 0-100}` |

Si el parlante no responde, la API devuelve `503` con `{"conectado": false}`.

## Pruebas sin hardware

```bat
.venv\Scripts\python -m pytest -q
```

Simulador del parlante para probar a mano:

```bat
.venv\Scripts\python -m simulador.arylic_falso --puerto 8099
```

y en `config.toml`: `[arylic] ip = "127.0.0.1:8099"`.
