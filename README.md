# Sistema de Mensajería Distribuida

Plataforma de mensajería entre usuarios sobre una arquitectura **cliente-servidor distribuida**, desarrollada en **C** y **Python**. El sistema combina tres tecnologías de comunicación —sockets TCP, ONC-RPC y HTTP— e incluye transferencia de ficheros directa entre clientes (peer-to-peer) sin pasar por el servidor.

## Arquitectura

El sistema se compone de cuatro servicios independientes que cooperan mediante distintos protocolos:

| Componente | Lenguaje | Tecnología | Responsabilidad |
|---|---|---|---|
| **Servidor de mensajería** | C | Sockets TCP + hilos POSIX | Registro/conexión de usuarios, entrega de mensajes y coordinación de adjuntos. Concurrente: un hilo por petición. |
| **Servidor RPC de registro** | C | ONC-RPC (libtirpc) | Registro (logging) remoto de las operaciones del servidor de mensajería. |
| **Servicio web de normalización** | Python | HTTP (`http.server`) | Normaliza los mensajes (colapsa espacios en blanco) antes de su envío. |
| **Cliente** | Python | Sockets TCP + HTTP | Interfaz de línea de comandos para el usuario final. |

La transferencia de ficheros adjuntos se realiza **directamente entre el cliente emisor y el receptor**: el servidor solo intermedia la señalización, no el contenido del fichero.

```
  Cliente A ──TCP──> Servidor de mensajería ──RPC──> Servidor de logging
     │  ▲                     │
     │  └──HTTP── Servicio web de normalización
     │
     └────────TCP (transferencia directa de ficheros)────────> Cliente B
```

## Características destacadas

- **Protocolo de comunicación propio** sobre sockets, con envío/recepción exacta de bytes, cadenas terminadas en `\0` y códigos de respuesta (`send_all` / `recv_all` / `send_string`).
- **Concurrencia** en el servidor mediante hilos POSIX, con acceso sincronizado a las estructuras compartidas de usuarios y mensajes.
- **Integración de tres paradigmas de comunicación** distribuida en un mismo sistema: sockets, RPC y servicios web.
- **Transferencia de ficheros peer-to-peer** que descarga al servidor del tráfico de datos.
- **Logging desacoplado**: si el servidor RPC no está disponible, el servidor de mensajería sigue operando sin él.
- **Batería de 64 pruebas automáticas** que cubren servidor, cliente y servicio RPC.

## Requisitos

- GCC con soporte para pthreads
- `libtirpc` (ONC-RPC): `sudo apt install libtirpc-dev`
- `rpcbind` en ejecución para el servidor RPC: `sudo service rpcbind start`
- Python 3.6 o superior (solo biblioteca estándar, sin dependencias externas)

## Compilación

```bash
make          # compila ambos servidores (mensajería y RPC)
make server   # solo el servidor de mensajería
make rpc      # solo el servidor RPC de logging
make clean    # elimina objetos y binarios
```

Se generan dos binarios: `server` y `log_rpc_server`.

## Ejecución

Los componentes deben arrancarse en este orden:

```bash
# 1. Servicio web de normalización (en cada máquina cliente)
python3 web/web_service.py                 # escucha en http://localhost:8000

# 2. Servidor RPC de registro (opcional pero recomendado)
./log_rpc_server

# 3. IP del servidor RPC (127.0.0.1 si es local; omitir para arrancar sin logging)
export LOG_RPC_IP=127.0.0.1

# 4. Servidor de mensajería
./server -p 8888

# 5. Cliente (en cada máquina cliente)
python3 client.py -s <IP_SERVIDOR> -p 8888
```

## Comandos del cliente

Una vez arrancado el cliente se muestra el prompt `c>` y se aceptan:

```
REGISTER <userName>                                  Registra un usuario
UNREGISTER <userName>                                Da de baja un usuario
CONNECT <userName>                                   Conecta al usuario
DISCONNECT <userName>                                Desconecta al usuario
USERS                                                Lista usuarios conectados
SEND <userName> <message>                            Envía un mensaje
SENDATTACH <userName> <message> <fileName>           Envía un mensaje con adjunto
GETFILE <userName> <fileName> <localFileName>        Descarga un adjunto
QUIT                                                 Sale del cliente
```

## Pruebas

```bash
python3 tests/run_tests.py -s localhost -p 8888                  # suite completa (64 pruebas)
python3 tests/run_tests.py -s localhost -p 8888 --suite <suite>  # por suite
```

## Estructura del proyecto

```
.
├── src/              Servidor de mensajería y módulos en C (protocolo, usuarios, mensajes, cliente RPC)
├── include/          Cabeceras
├── rpc/              Servidor RPC de logging
│   ├── log_rpc.x         Definición de la interfaz RPC
│   └── generated/        Stubs generados por rpcgen
├── web/              Servicio web de normalización (Python)
├── tests/            Batería de pruebas automáticas (Python)
├── client.py         Cliente de línea de comandos (Python)
└── Makefile
```
