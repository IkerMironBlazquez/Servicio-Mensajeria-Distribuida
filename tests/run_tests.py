#!/usr/bin/env python3
import argparse
import socket
import subprocess
import threading
import time
import os
import sys
import tempfile
import hashlib

#Directorio raiz del proyecto
_WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#CONFIGURACION

#Timeout en segundos para recibir mensajes
ASYNC_TIMEOUT = 3.0

#Puerto base para los hilos receptores de los clientes simulados
LISTENER_BASE_PORT = 19000

#CONTADORES GLOBALES

_total  = 0
_passed = 0
_failed = 0


#FUNCIONES DE IMPRESION

def _print_suite_header(title, subtitle):
    print()
    print("=" * 77)
    print(title)
    print(subtitle)
    print("=" * 77)

def _print_block(title):
    print()
    print("--- " + title + " ---")

def _print_result(name, passed, got=None, expected=None):
    global _total, _passed, _failed
    _total += 1
    if passed:
        _passed += 1
        print("[ OK ] " + name)
    else:
        _failed += 1
        msg = "[ERROR] " + name
        if expected is not None:
            msg += "  (esperado: " + repr(expected) + ")"
        if got is not None:
            msg += "  (recibido: " + repr(got) + ")"
        print(msg)

def _print_summary():
    print()
    print("=" * 77)
    print("RESUMEN: {}/{} pruebas pasaron".format(_passed, _total))
    if _failed:
        print("{} pruebas fallaron".format(_failed))
    print("=" * 77)


#PROTOCOLO DE COMUNICACION 

def _send_string(sock, text):
    """Envia la cadena text codificada en UTF-8 seguida del caracter nulo."""
    sock.sendall(text.encode('utf-8') + b'\x00')

def _recv_string(sock, max_len=4096):
    """Recibe bytes del socket hasta encontrar el caracter nulo.
    Devuelve la cadena decodificada, o None si se cierra la conexion."""
    data = b""
    while len(data) < max_len:
        b = sock.recv(1)
        if not b:
            return None
        if b == b'\x00':
            return data.decode('utf-8', errors='replace')
        data += b
    return None

def _recv_code(sock):
    """Recibe un byte de codigo de respuesta. Devuelve el entero o None."""
    data = sock.recv(1)
    if not data:
        return None
    return data[0]

def _new_conn(server, port):
    """Abre una conexion TCP nueva al servidor y la devuelve."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((server, port))
    return s


#OPERACIONES DEL PROTOCOLO, igual que cliente

def op_register(server, port, username):
    """Envia REGISTER y devuelve el codigo de respuesta."""
    s = _new_conn(server, port)
    _send_string(s, "REGISTER")
    _send_string(s, username)
    code = _recv_code(s)
    s.close()
    return code

def op_unregister(server, port, username):
    """Envia UNREGISTER y devuelve el codigo de respuesta."""
    s = _new_conn(server, port)
    _send_string(s, "UNREGISTER")
    _send_string(s, username)
    code = _recv_code(s)
    s.close()
    return code

def op_connect(server, port, username, listen_port):
    """Envia CONNECT con el puerto de escucha del hilo receptor.
    Devuelve el codigo de respuesta."""
    s = _new_conn(server, port)
    _send_string(s, "CONNECT")
    _send_string(s, username)
    _send_string(s, str(listen_port))
    code = _recv_code(s)
    s.close()
    return code

def op_disconnect(server, port, username):
    """Envia DISCONNECT y devuelve el codigo de respuesta."""
    s = _new_conn(server, port)
    _send_string(s, "DISCONNECT")
    _send_string(s, username)
    code = _recv_code(s)
    s.close()
    return code

def op_send(server, port, remitente, destinatario, mensaje):
    """Envia SEND y devuelve (codigo, msg_id_str)."""
    s = _new_conn(server, port)
    _send_string(s, "SEND")
    _send_string(s, remitente)
    _send_string(s, destinatario)
    _send_string(s, mensaje)
    code = _recv_code(s)
    msg_id = None
    if code == 0:
        msg_id = _recv_string(s)
    s.close()
    return code, msg_id

def op_sendattach(server, port, remitente, destinatario, mensaje, fichero):
    """Envia SENDATTACH y devuelve (codigo, msg_id_str)."""
    s = _new_conn(server, port)
    _send_string(s, "SENDATTACH")
    _send_string(s, remitente)
    _send_string(s, destinatario)
    _send_string(s, mensaje)
    _send_string(s, fichero)
    code = _recv_code(s)
    msg_id = None
    if code == 0:
        msg_id = _recv_string(s)
    s.close()
    return code, msg_id

def op_users(server, port, username):
    """Envia USERS y devuelve (codigo, lista_de_cadenas)."""
    s = _new_conn(server, port)
    _send_string(s, "USERS")
    _send_string(s, username)
    code = _recv_code(s)
    entries = []
    if code == 0:
        num_str = _recv_string(s)
        num = int(num_str)
        for _ in range(num):
            e = _recv_string(s)
            entries.append(e)
    s.close()
    return code, entries


#CLIENTE SIMULADO CON HILO RECEPTOR

class SimulatedClient:
    """
    Simula un cliente conectado con su hilo receptor.
    """

    def __init__(self, server, port, username):
        self.server = server
        self.port = port
        self.username = username

        # Mensajes recibidos (tuples segun tipo)
        self.received_messages = []  # (msg_id, remitente, texto)
        self.received_attachments = []  # (msg_id, remitente, texto, fichero)
        self.received_send_acks = []  # msg_id
        self.received_attach_acks = []  # (msg_id, fichero)

        self._lock = threading.Lock()
        self._running = False
        self._sock = None
        self._thread = None
        self.listen_port = None

    def start(self):
        """Crea el socket de escucha y lanza el hilo receptor."""
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(('', 0))
        self._sock.listen(5)
        self._sock.settimeout(0.5)
        self.listen_port = self._sock.getsockname()[1]
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def connect_to_server(self):
        """Envia CONNECT al servidor con el puerto de escucha ya creado.
        Devuelve el codigo de respuesta."""
        return op_connect(self.server, self.port, self.username, self.listen_port)

    def stop(self):
        """Para el hilo receptor y cierra el socket."""
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _loop(self):
        """Bucle del hilo receptor: acepta conexiones y procesa operaciones."""
        while self._running:
            try:
                conn, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                op = _recv_string(conn)
                if op is None:
                    continue

                if op == "SEND MESSAGE":
                    remitente = _recv_string(conn)
                    msg_id = _recv_string(conn)
                    texto = _recv_string(conn)
                    with self._lock:
                        self.received_messages.append((msg_id, remitente, texto))

                elif op == "SEND MESS ACK":
                    msg_id = _recv_string(conn)
                    with self._lock:
                        self.received_send_acks.append(msg_id)

                elif op == "SEND MESSAGE ATTACH":
                    remitente = _recv_string(conn)
                    msg_id = _recv_string(conn)
                    texto = _recv_string(conn)
                    fichero = _recv_string(conn)
                    with self._lock:
                        self.received_attachments.append((msg_id, remitente, texto, fichero))

                elif op == "SEND MESS ATTACH ACK":
                    msg_id  = _recv_string(conn)
                    fichero = _recv_string(conn)
                    with self._lock:
                        self.received_attach_acks.append((msg_id, fichero))

                elif op == "GET FILE":
                    # Otro cliente solicita un fichero
                    _solicitante = _recv_string(conn)
                    fichero = _recv_string(conn)
                    _send_file_content(conn, fichero)

            except Exception:
                pass
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    def wait_for_message(self, timeout=ASYNC_TIMEOUT):
        """Espera hasta que llegue al menos un mensaje de texto o se agote el timeout."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                if self.received_messages:
                    return True
            time.sleep(0.05)
        return False

    def wait_for_attachment(self, timeout=ASYNC_TIMEOUT):
        """Espera hasta que llegue al menos un mensaje con adjunto."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                if self.received_attachments:
                    return True
            time.sleep(0.05)
        return False

    def wait_for_send_ack(self, timeout=ASYNC_TIMEOUT):
        """Espera hasta que llegue al menos un ACK de SEND."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                if self.received_send_acks:
                    return True
            time.sleep(0.05)
        return False

    def wait_for_attach_ack(self, timeout=ASYNC_TIMEOUT):
        """Espera hasta que llegue al menos un ACK de SENDATTACH."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                if self.received_attach_acks:
                    return True
            time.sleep(0.05)
        return False


#FUNCIONES AUXILIARES DE TRANSFERENCIA DE FICHERO (para el hilo receptor)

def _send_file_content(sock, path):
    """Envia el contenido de un fichero: primero el tamano como cadena, luego los bytes."""
    try:
        with open(path, 'rb') as f:
            content = f.read()
        _send_string(sock, str(len(content)))
        if len(content) > 0:
            sock.sendall(content)
    except OSError:
        _send_string(sock, "-1")

def _recv_file_content(sock, local_path):
    """Recibe el contenido de un fichero y lo guarda en local_path.
    Devuelve True en exito, False si el remoto indico error (tamano -1)."""
    size_str = _recv_string(sock)
    if size_str is None:
        return False
    size = int(size_str)
    if size < 0:
        return False
    content = b""
    while len(content) < size:
        chunk = sock.recv(size - len(content))
        if not chunk:
            return False
        content += chunk
    try:
        with open(local_path, 'wb') as f:
            f.write(content)
    except OSError:
        return False
    return True

def getfile_from_client(remote_ip, remote_port, solicitante, fichero_remoto, local_path):
    """Conecta al hilo receptor del cliente remoto y descarga el fichero.
    Devuelve True en exito, False en error."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((remote_ip, int(remote_port)))
        _send_string(s, "GET FILE")
        _send_string(s, solicitante)
        _send_string(s, fichero_remoto)
        ok = _recv_file_content(s, local_path)
        s.close()
        return ok
    except Exception:
        return False


#FUNCION AUXILIAR: limpiar estado entre suites

def _cleanup(server, port, *usernames):
    """Intenta desregistrar los usuarios de prueba ignorando errores."""
    for u in usernames:
        try:
            op_disconnect(server, port, u)
        except Exception:
            pass
        try:
            op_unregister(server, port, u)
        except Exception:
            pass


#SUITE 1: PRUEBAS BASICAS (1-23)

def run_suite_basica(server, port):
    _print_suite_header(
        "PRUEBAS BASICAS - Parte 1",
        "Pruebas 1-23: REGISTER, UNREGISTER, CONNECT, DISCONNECT, SEND y USERS"
    )

    _cleanup(server, port, "alice", "bob", "carol", "temp", "remitente", "destino")

    # Verifica el registro de usuarios: caso OK, duplicado y varios usuarios.
    _print_block("BLOQUE 1 - REGISTER (pruebas 1-3)")

    #Prueba 1: Registrar usuario nuevo
    code = op_register(server, port, "alice")
    _print_result("Prueba 1: Registrar usuario nuevo",
                    code == 0, got=code, expected=0)

    #Prueba 2: Registrar usuario duplicado
    code = op_register(server, port, "alice")
    _print_result("Prueba 2: Registrar usuario duplicado (USERNAME IN USE)",
                    code == 1, got=code, expected=1)

    #Prueba 3: Registrar varios usuarios
    code_bob   = op_register(server, port, "bob")
    code_carol = op_register(server, port, "carol")
    _print_result("Prueba 3: Registrar varios usuarios",
                    code_bob == 0 and code_carol == 0,
                    got=(code_bob, code_carol), expected=(0, 0))

    #Verifica la baja de usuarios: caso OK, inexistente y borrado de pendientes.
    _print_block("BLOQUE 2 - UNREGISTER (pruebas 4-6)")

    #Prueba 4: Dar de baja usuario existente
    op_register(server, port, "temp")
    code = op_unregister(server, port, "temp")
    _print_result("Prueba 4: Dar de baja usuario existente",
                    code == 0, got=code, expected=0)

    #Prueba 5: Dar de baja usuario inexistente
    code = op_unregister(server, port, "noexiste")
    _print_result("Prueba 5: Dar de baja usuario inexistente (USER DOES NOT EXIST)",
                    code == 1, got=code, expected=1)

    #Prueba 6: Dar de baja borra mensajes pendientes
    op_register(server, port, "remitente")
    op_register(server, port, "destino")

    cli_rem = SimulatedClient(server, port, "remitente")
    cli_rem.start()
    cli_rem.connect_to_server()

    #Enviar mensajes a destino desconectado para que queden pendientes
    op_send(server, port, "remitente", "destino", "pendiente 1")
    op_send(server, port, "remitente", "destino", "pendiente 2")

    #Dar de baja a destino (debe borrar pendientes) y registrarlo de nuevo
    op_unregister(server, port, "destino")
    op_register(server, port, "destino")

    #Conectar destino: no debe recibir mensajes del usuario anterior
    cli_dest = SimulatedClient(server, port, "destino")
    cli_dest.start()
    cli_dest.connect_to_server()
    got_pending = cli_dest.wait_for_message(timeout=1.5)
    cli_dest.stop()
    cli_rem.stop()

    _print_result("Prueba 6: Dar de baja borra mensajes pendientes",
                    not got_pending,
                    got="mensaje pendiente recibido" if got_pending else "sin pendientes",
                    expected="sin pendientes")

    _cleanup(server, port, "remitente", "destino")

    #Verifica la conexion de usuarios: caso OK, inexistente y doble conexion.
    _print_block("BLOQUE 3 - CONNECT (pruebas 7-10)")

    #Prueba 7: Conectar usuario registrado
    cli_alice = SimulatedClient(server, port, "alice")
    cli_alice.start()
    code = cli_alice.connect_to_server()
    _print_result("Prueba 7: Conectar usuario registrado",
                    code == 0, got=code, expected=0)

    #Prueba 8: Conectar usuario inexistente
    cli_x = SimulatedClient(server, port, "noexiste")
    cli_x.start()
    code = cli_x.connect_to_server()
    cli_x.stop()
    _print_result("Prueba 8: Conectar usuario inexistente (USER DOES NOT EXIST)",
                    code == 1, got=code, expected=1)

    #Prueba 9: Conectar dos veces el mismo usuario (alice ya esta conectada)
    cli_alice2 = SimulatedClient(server, port, "alice")
    cli_alice2.start()
    code = cli_alice2.connect_to_server()
    cli_alice2.stop()
    _print_result("Prueba 9: Conectar dos veces el mismo usuario (USER ALREADY CONNECTED)",
                    code == 2, got=code, expected=2)

    #Prueba 10: Conectar un usuario distinto desde otra sesion debe funcionar
    cli_carol = SimulatedClient(server, port, "carol")
    cli_carol.start()
    code = cli_carol.connect_to_server()
    _print_result("Prueba 10: Conectar segundo usuario en cliente distinto (OK desde otra sesion)",
                    code == 0, got=code, expected=0)

    #Verifica la desconexion: caso OK, usuario inexistente y ya desconectado.
    _print_block("BLOQUE 4 - DISCONNECT (pruebas 11-14)")

    #Prueba 11: Desconectar usuario conectado (alice)
    code = op_disconnect(server, port, "alice")
    cli_alice.stop()
    _print_result("Prueba 11: Desconectar usuario conectado",
                    code == 0, got=code, expected=0)

    #Prueba 12: Desconectar usuario inexistente
    code = op_disconnect(server, port, "fantasma")
    _print_result("Prueba 12: Desconectar usuario inexistente (USER DOES NOT EXIST)",
                    code == 1, got=code, expected=1)

    #Prueba 13: Desconectar usuario no conectado (alice ya desconectada)
    code = op_disconnect(server, port, "alice")
    _print_result("Prueba 13: Desconectar usuario no conectado (USER NOT CONNECTED)",
                    code == 2, got=code, expected=2)

    #Prueba 14: Verificar que el hilo receptor se para al desconectar
    cli_alice = SimulatedClient(server, port, "alice")
    cli_alice.start()
    port_antes = cli_alice.listen_port
    cli_alice.connect_to_server()
    op_disconnect(server, port, "alice")
    cli_alice.stop()
    #Comprobar que el puerto queda libre (ya no acepta conexiones)
    tiempo_libre = False
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.5)
        probe.connect(('127.0.0.1', port_antes))
        probe.close()
    except (ConnectionRefusedError, socket.timeout, OSError):
        tiempo_libre = True
    _print_result("Prueba 14: Puerto del hilo receptor queda libre tras DISCONNECT",
                    tiempo_libre)

    #Reconectar alice para las siguientes pruebas
    cli_alice = SimulatedClient(server, port, "alice")
    cli_alice.start()
    cli_alice.connect_to_server()

    #Verifica el envio de mensajes: entrega inmediata, pendiente e inexistente.
    _print_block("BLOQUE 5 - SEND (pruebas 15-20)")

    #Prueba 15: Enviar mensaje a usuario conectado (alice -> bob)
    cli_bob = SimulatedClient(server, port, "bob")
    cli_bob.start()
    cli_bob.connect_to_server()

    code, msg_id = op_send(server, port, "alice", "bob", "hola que tal")
    _print_result("Prueba 15: Enviar mensaje a usuario conectado (SEND OK)",
                    code == 0, got=code, expected=0)

    #Prueba 18: Comprobar que bob recibe el mensaje
    bob_got = cli_bob.wait_for_message()
    if bob_got:
        mid, rem, txt = cli_bob.received_messages[-1]
        _print_result("Prueba 18: Bob recibe MESSAGE <id> FROM alice",
                        rem == "alice" and mid == msg_id,
                        got=(mid, rem), expected=(msg_id, "alice"))
    else:
        _print_result("Prueba 18: Bob recibe MESSAGE <id> FROM alice", False,
                        got="timeout sin mensaje")

    #Prueba 19: Comprobar ACK en alice
    alice_ack = cli_alice.wait_for_send_ack()
    if alice_ack:
        ack_id = cli_alice.received_send_acks[-1]
        _print_result("Prueba 19: Alice recibe SEND MESSAGE <id> OK (ACK)",
                        ack_id == msg_id, got=ack_id, expected=msg_id)
    else:
        _print_result("Prueba 19: Alice recibe SEND MESSAGE <id> OK (ACK)", False,
                        got="timeout sin ACK")

    #Prueba 16: Enviar mensaje a usuario desconectado
    op_disconnect(server, port, "bob")
    cli_bob.stop()
    cli_bob2 = SimulatedClient(server, port, "bob")  # ya no conectado al servidor
    cli_bob2.start()

    code2, msg_id2 = op_send(server, port, "alice", "bob", "mensaje pendiente")
    _print_result("Prueba 16: Enviar mensaje a usuario desconectado (SEND OK, queda pendiente)",
                    code2 == 0, got=code2, expected=0)
    cli_bob2.stop()

    #Prueba 17: Enviar mensaje a usuario inexistente
    code3, _ = op_send(server, port, "alice", "fantasma", "hola")
    _print_result("Prueba 17: Enviar mensaje a usuario inexistente (USER DOES NOT EXIST)",
                    code3 == 1, got=code3, expected=1)

    #Prueba 20: Entrega de pendientes al reconectar
    cli_bob = SimulatedClient(server, port, "bob")
    cli_bob.start()
    cli_bob.connect_to_server()

    bob_got_pending = cli_bob.wait_for_message()
    if bob_got_pending:
        mid_p, rem_p, txt_p = cli_bob.received_messages[-1]
        _print_result("Prueba 20: Entrega de mensajes pendientes al conectar",
                        rem_p == "alice" and mid_p == msg_id2,
                        got=(mid_p, rem_p), expected=(msg_id2, "alice"))
    else:
        _print_result("Prueba 20: Entrega de mensajes pendientes al conectar", False,
                        got="timeout sin pendientes")

    #Verifica el listado de usuarios conectados: formato y casos de error.
    _print_block("BLOQUE 6 - USERS (pruebas 21-23)")

    #Prueba 21: Pedir usuarios estando conectado
    code, entries = op_users(server, port, "alice")
    _print_result("Prueba 21: USERS estando conectado (OK)",
                    code == 0, got=code, expected=0)
    if code == 0:
        nombres = [e.split("::")[0].strip() for e in entries]
        alice_en_lista = "alice" in nombres
        bob_en_lista   = "bob" in nombres
        _print_result("Prueba 21b: Alice y bob aparecen en la lista de usuarios",
                        alice_en_lista and bob_en_lista,
                        got=nombres, expected=["alice", "bob", "..."])
        _print_result("Prueba 21c: Las entradas tienen formato usuario :: IP :: puerto",
                        all(len(e.split("::")) == 3 for e in entries),
                        got=entries)

    #Prueba 22: Pedir usuarios sin estar conectado
    op_disconnect(server, port, "alice")
    cli_alice.stop()
    code_nc, _ = op_users(server, port, "alice")
    _print_result("Prueba 22: USERS sin estar conectado (USER IS NOT CONNECTED)",
                    code_nc == 1, got=code_nc, expected=1)

    #Prueba 23: USERS con varios clientes conectados
    cli_alice = SimulatedClient(server, port, "alice")
    cli_alice.start()
    cli_alice.connect_to_server()

    code3, entries3 = op_users(server, port, "alice")
    if code3 == 0:
        nombres3 = [e.split("::")[0].strip() for e in entries3]
        _print_result("Prueba 23: USERS con varios clientes (alice, bob, carol conectados)",
                        len(entries3) >= 2,
                        got=nombres3)
    else:
        _print_result("Prueba 23: USERS con varios clientes", False,
                        got=code3, expected=0)

    #Limpieza final
    op_disconnect(server, port, "alice")
    op_disconnect(server, port, "bob")
    op_disconnect(server, port, "carol")
    cli_alice.stop()
    cli_bob.stop()
    cli_carol.stop()
    _cleanup(server, port, "alice", "bob", "carol")


#SUITE 2: MENSAJES PENDIENTES Y CONCURRENCIA (24-26)

def run_suite_pendientes(server, port):
    _print_suite_header(
        "PRUEBAS DE MENSAJES PENDIENTES Y CONCURRENCIA",
        "Pruebas 24-26: Concurrencia, acumulacion de pendientes y desconexion brusca"
    )

    _cleanup(server, port, "alice", "bob", "carol")
    op_register(server, port, "alice")
    op_register(server, port, "bob")
    op_register(server, port, "carol")

    #Verifica que el servidor maneja correctamente envios concurrentes sin perder mensajes.
    _print_block("BLOQUE 7 - CONCURRENCIA (prueba 24)")

    #Conectar los tres usuarios
    cli_alice = SimulatedClient(server, port, "alice")
    cli_bob   = SimulatedClient(server, port, "bob")
    cli_carol = SimulatedClient(server, port, "carol")
    for c in (cli_alice, cli_bob, cli_carol):
        c.start()
        c.connect_to_server()

    #Lanzar envios concurrentes desde hilos
    errores_concurrencia = []
    def send_concurrent(rem, dest, msg):
        code, _ = op_send(server, port, rem, dest, msg)
        if code != 0:
            errores_concurrencia.append((rem, dest, code))

    hilos = [
        threading.Thread(target=send_concurrent, args=("alice", "bob",   "alice->bob   mensaje")),
        threading.Thread(target=send_concurrent, args=("alice", "carol", "alice->carol mensaje")),
        threading.Thread(target=send_concurrent, args=("bob",   "alice", "bob->alice   mensaje")),
        threading.Thread(target=send_concurrent, args=("bob",   "carol", "bob->carol   mensaje")),
        threading.Thread(target=send_concurrent, args=("carol", "alice", "carol->alice mensaje")),
        threading.Thread(target=send_concurrent, args=("carol", "bob",   "carol->bob   mensaje")),
    ]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    #Dar tiempo a que lleguen todos los mensajes
    time.sleep(1.5)

    _print_result("Prueba 24: Varios clientes enviando mensajes a la vez sin errores",
                    len(errores_concurrencia) == 0,
                    got=errores_concurrencia if errores_concurrencia else "sin errores")

    _print_result("Prueba 24b: Alice recibio mensajes de bob y carol",
                    len(cli_alice.received_messages) >= 2,
                    got=len(cli_alice.received_messages), expected=">=2")

    _print_result("Prueba 24c: Bob recibio mensajes de alice y carol",
                    len(cli_bob.received_messages) >= 2,
                    got=len(cli_bob.received_messages), expected=">=2")

    for c in (cli_alice, cli_bob, cli_carol):
        op_disconnect(server, port, c.username)
        c.stop()

    #Verifica la acumulacion y entrega ordenada (FIFO) de mensajes pendientes.
    _print_block("BLOQUE 8 - MULTIPLES PENDIENTES (prueba 25)")

    cli_alice = SimulatedClient(server, port, "alice")
    cli_alice.start()
    cli_alice.connect_to_server()
    #bob NO se conecta: todos los mensajes quedan pendientes

    NUM_PENDIENTES = 5
    ids_enviados = []
    for i in range(1, NUM_PENDIENTES + 1):
        code, mid = op_send(server, port, "alice", "bob", "pendiente numero {}".format(i))
        if code == 0:
            ids_enviados.append(mid)

    _print_result("Prueba 25: Alice envia {} mensajes a bob desconectado".format(NUM_PENDIENTES),
                    len(ids_enviados) == NUM_PENDIENTES,
                    got=len(ids_enviados), expected=NUM_PENDIENTES)

    #Conectar bob: debe recibir los pendientes en orden
    cli_bob = SimulatedClient(server, port, "bob")
    cli_bob.start()
    cli_bob.connect_to_server()

    deadline = time.time() + ASYNC_TIMEOUT
    while time.time() < deadline:
        with cli_bob._lock:
            if len(cli_bob.received_messages) >= NUM_PENDIENTES:
                break
        time.sleep(0.05)

    with cli_bob._lock:
        msgs_recibidos = list(cli_bob.received_messages)

    _print_result("Prueba 25b: Bob recibe los {} mensajes pendientes al conectar".format(NUM_PENDIENTES),
                    len(msgs_recibidos) == NUM_PENDIENTES,
                    got=len(msgs_recibidos), expected=NUM_PENDIENTES)

    #Verificar orden FIFO: los ids deben coincidir en orden
    ids_recibidos = [m[0] for m in msgs_recibidos]
    _print_result("Prueba 25c: Los mensajes pendientes se entregan en orden de llegada (FIFO)",
                    ids_recibidos == ids_enviados,
                    got=ids_recibidos, expected=ids_enviados)

    for c in (cli_alice, cli_bob):
        op_disconnect(server, port, c.username)
        c.stop()

    #Verifica que una caida brusca del receptor deja el mensaje como pendiente.
    _print_block("BLOQUE 9 - DESCONEXION DURANTE ENTREGA (prueba 26)")

    cli_alice = SimulatedClient(server, port, "alice")
    cli_alice.start()
    cli_alice.connect_to_server()

    cli_bob = SimulatedClient(server, port, "bob")
    cli_bob.start()
    cli_bob.connect_to_server()

    #Parar el hilo receptor de bob sin hacer DISCONNECT (simula caida brusca)
    cli_bob.stop()
    time.sleep(0.2)

    #Alice intenta enviar a bob; la entrega debe fallar pero SEND debe devolver OK
    code, mid = op_send(server, port, "alice", "bob", "mensaje cuando bob no escucha")
    _print_result("Prueba 26: SEND devuelve OK aunque el destinatario haya caido",
                    code == 0, got=code, expected=0)

    #El mensaje debe quedar pendiente; reconectar bob y verificar
    cli_bob2 = SimulatedClient(server, port, "bob")
    cli_bob2.start()
    cli_bob2.connect_to_server()
    got_after_reconnect = cli_bob2.wait_for_message()
    _print_result("Prueba 26b: El mensaje queda pendiente y se entrega al reconectarse",
                    got_after_reconnect,
                    got="mensaje recibido" if got_after_reconnect else "timeout sin mensaje")

    for c in (cli_alice, cli_bob2):
        op_disconnect(server, port, c.username)
        c.stop()

    _cleanup(server, port, "alice", "bob", "carol")


#SUITE 3: ADJUNTOS Y GETFILE (27-37)

def run_suite_adjuntos(server, port):
    _print_suite_header(
        "PRUEBAS DE ADJUNTOS Y GETFILE - Parte 2",
        "Pruebas 27-37: SENDATTACH y transferencia directa de ficheros entre clientes"
    )

    _cleanup(server, port, "alice", "bob")
    op_register(server, port, "alice")
    op_register(server, port, "bob")

    #Crear fichero de prueba temporal
    tmp_src = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
    tmp_src.write(b"Contenido del fichero de prueba para adjuntos\n")
    tmp_src.close()
    fichero_prueba = tmp_src.name

    #Verifica SENDATTACH: entrega inmediata con adjunto, pendiente y ACK al remitente.
    _print_block("BLOQUE 10 - SENDATTACH (pruebas 27-31)")

    cli_alice = SimulatedClient(server, port, "alice")
    cli_bob   = SimulatedClient(server, port, "bob")
    cli_alice.start()
    cli_bob.start()
    cli_alice.connect_to_server()
    cli_bob.connect_to_server()

    #Prueba 27: SENDATTACH a usuario conectado
    code, mid = op_sendattach(server, port, "alice", "bob",
                                "hola adjunto de prueba", fichero_prueba)
    _print_result("Prueba 27: SENDATTACH a usuario conectado (OK)",
                    code == 0, got=code, expected=0)

    #Prueba 31: Bob recibe el mensaje con la linea FILE
    bob_got_att = cli_bob.wait_for_attachment()
    if bob_got_att:
        a_mid, a_rem, a_txt, a_fich = cli_bob.received_attachments[-1]
        _print_result("Prueba 31: Bob recibe MESSAGE con FILE (formato correcto)",
                        a_rem == "alice" and a_fich == fichero_prueba and a_mid == mid,
                        got=(a_mid, a_rem, a_fich),
                        expected=(mid, "alice", fichero_prueba))
    else:
        _print_result("Prueba 31: Bob recibe MESSAGE con FILE", False, got="timeout sin mensaje")

    #Prueba 30: Alice recibe ACK de SENDATTACH
    alice_got_ack = cli_alice.wait_for_attach_ack()
    if alice_got_ack:
        ack_mid, ack_fich = cli_alice.received_attach_acks[-1]
        _print_result("Prueba 30: Alice recibe SENDATTACH MESSAGE <id> <file> OK (ACK)",
                        ack_mid == mid and ack_fich == fichero_prueba,
                        got=(ack_mid, ack_fich), expected=(mid, fichero_prueba))
    else:
        _print_result("Prueba 30: Alice recibe SENDATTACH MESSAGE <id> <file> OK (ACK)",
                        False, got="timeout sin ACK")

    #Prueba 28: SENDATTACH a usuario desconectado
    op_disconnect(server, port, "bob")
    cli_bob.stop()

    code2, mid2 = op_sendattach(server, port, "alice", "bob",
                                "mensaje con adjunto pendiente", fichero_prueba)
    _print_result("Prueba 28: SENDATTACH a usuario desconectado (queda pendiente)",
                    code2 == 0, got=code2, expected=0)

    #Prueba 29: Entrega pendiente de SENDATTACH al conectar
    cli_bob = SimulatedClient(server, port, "bob")
    cli_bob.start()
    cli_bob.connect_to_server()
    bob_got_pending_att = cli_bob.wait_for_attachment()
    if bob_got_pending_att:
        pa_mid, pa_rem, pa_txt, pa_fich = cli_bob.received_attachments[-1]
        _print_result("Prueba 29: Entrega pendiente de SENDATTACH al conectar",
                        pa_mid == mid2 and pa_fich == fichero_prueba,
                        got=(pa_mid, pa_fich), expected=(mid2, fichero_prueba))
    else:
        _print_result("Prueba 29: Entrega pendiente de SENDATTACH al conectar",
                        False, got="timeout sin pendiente")

    #Verifica GETFILE: descarga directa entre clientes usando la IP y puerto de USERS.
    _print_block("BLOQUE 11 - GETFILE (pruebas 32-37)")

    #Obtener IP y puerto de alice mediante USERS para poder conectarse directamente
    code_u, entries = op_users(server, port, "alice")
    alice_info = None
    if code_u == 0:
        for e in entries:
            parts = [p.strip() for p in e.split("::")]
            if len(parts) == 3 and parts[0] == "alice":
                alice_info = (parts[1], int(parts[2]))
                break

    # Prueba 32: USERS actualiza la info necesaria para GETFILE
    _print_result("Prueba 32: USERS devuelve IP y puerto de alice para GETFILE",
                    alice_info is not None,
                    got=alice_info)

    if alice_info:
        alice_ip, alice_port_listen = alice_info

        #Prueba 33: Descargar fichero de usuario conectado
        tmp_dst = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
        tmp_dst.close()
        ok = getfile_from_client(alice_ip, alice_port_listen, "bob",
                                    fichero_prueba, tmp_dst.name)
        if ok:
            with open(fichero_prueba, 'rb') as f:
                orig = f.read()
            with open(tmp_dst.name, 'rb') as f:
                copia = f.read()
            _print_result("Prueba 33: GETFILE descarga fichero de usuario conectado",
                            orig == copia,
                            got="contenido identico" if orig == copia else "contenido diferente")
        else:
            _print_result("Prueba 33: GETFILE descarga fichero de usuario conectado",
                            False, got="transferencia fallida")
        os.unlink(tmp_dst.name)

        #Prueba 35: Intentar descargar fichero inexistente
        tmp_dst2 = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
        tmp_dst2.close()
        ok2 = getfile_from_client(alice_ip, alice_port_listen, "bob",
                                    "/tmp/fichero_que_no_existe_jamas_xyz.txt",
                                    tmp_dst2.name)
        _print_result("Prueba 35: GETFILE falla con fichero inexistente en el remoto",
                        not ok2,
                        got="fallo correcto" if not ok2 else "exito inesperado")
        os.unlink(tmp_dst2.name)

        #Prueba 36: Descargar fichero vacio
        tmp_vacio = tempfile.NamedTemporaryFile(delete=False)
        tmp_vacio.close()  # fichero vacio
        tmp_dst3 = tempfile.NamedTemporaryFile(delete=False)
        tmp_dst3.close()
        ok3 = getfile_from_client(alice_ip, alice_port_listen, "bob",
                                    tmp_vacio.name, tmp_dst3.name)
        if ok3:
            size = os.path.getsize(tmp_dst3.name)
            _print_result("Prueba 36: GETFILE con fichero vacio (0 bytes)",
                            size == 0, got=size, expected=0)
        else:
            _print_result("Prueba 36: GETFILE con fichero vacio", False,
                            got="transferencia fallida")
        os.unlink(tmp_vacio.name)
        os.unlink(tmp_dst3.name)

        # Prueba 37: Descargar fichero grande
        tmp_grande = tempfile.NamedTemporaryFile(delete=False)
        tmp_grande.write(os.urandom(2 * 1024 * 1024))  # 2 MB de datos aleatorios
        tmp_grande.close()
        tmp_dst4 = tempfile.NamedTemporaryFile(delete=False)
        tmp_dst4.close()

        ok4 = getfile_from_client(alice_ip, alice_port_listen, "bob",
                                    tmp_grande.name, tmp_dst4.name)
        if ok4:
            md5_orig  = hashlib.md5(open(tmp_grande.name, 'rb').read()).hexdigest()
            md5_copia = hashlib.md5(open(tmp_dst4.name,   'rb').read()).hexdigest()
            _print_result("Prueba 37: GETFILE con fichero grande (2 MB, integridad MD5)",
                            md5_orig == md5_copia,
                            got=md5_copia, expected=md5_orig)
        else:
            _print_result("Prueba 37: GETFILE con fichero grande", False,
                            got="transferencia fallida")
        os.unlink(tmp_grande.name)
        os.unlink(tmp_dst4.name)

    #Prueba 34: Intentar GETFILE de usuario desconectado
    op_disconnect(server, port, "alice")
    cli_alice.stop()
    #Con alice desconectada, su puerto de escucha ya no acepta conexiones
    if alice_info:
        tmp_dst5 = tempfile.NamedTemporaryFile(delete=False)
        tmp_dst5.close()
        ok5 = getfile_from_client(alice_ip, alice_port_listen, "bob",
                                    fichero_prueba, tmp_dst5.name)
        _print_result("Prueba 34: GETFILE falla si el usuario esta desconectado",
                        not ok5,
                        got="fallo correcto" if not ok5 else "exito inesperado")
        os.unlink(tmp_dst5.name)

    op_disconnect(server, port, "bob")
    cli_bob.stop()
    os.unlink(fichero_prueba)
    _cleanup(server, port, "alice", "bob")


#SUITE 4: SERVICIO WEB (38-39)

def run_suite_web(server, port):
    _print_suite_header(
        "PRUEBAS DEL SERVICIO WEB DE NORMALIZACION",
        "Pruebas 38-39: Normalizacion de mensajes con espacios repetidos"
    )

    #Verificar que el servicio web esta levantado antes de las pruebas
    try:
        import urllib.request
        import json
        data = json.dumps({"message": "test"}).encode('utf-8')
        req = urllib.request.Request(
            'http://localhost:8000/normalize',
            data=data,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            pass
    except Exception:
        print()
        print("[AVISO] El servicio web no responde en localhost:8000.")
        print("        Arrancalo con: python3 web/web_service.py")
        print("        Las pruebas 38-39 se omiten.")
        return

    _cleanup(server, port, "alice", "bob")
    op_register(server, port, "alice")
    op_register(server, port, "bob")

    cli_alice = SimulatedClient(server, port, "alice")
    cli_bob   = SimulatedClient(server, port, "bob")
    cli_alice.start()
    cli_bob.start()
    cli_alice.connect_to_server()
    cli_bob.connect_to_server()

    def normalize_via_web(text):
        """Llama al servicio web local y devuelve el mensaje normalizado."""
        try:
            import urllib.request
            import json
            data = json.dumps({"message": text}).encode('utf-8')
            req = urllib.request.Request(
                'http://localhost:8000/normalize',
                data=data,
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=2) as resp:
                result = json.loads(resp.read().decode('utf-8'))
                return result.get("message", None)
        except Exception:
            return None

    #Verifica la normalizacion de espacios en mensajes a traves del servicio web.
    _print_block("BLOQUE 12 - SERVICIO WEB (pruebas 38-39)")

    #Prueba 38: El servicio web elimina espacios repetidos antes de enviar
    mensaje_crudo = "hola      que      tal"
    esperado      = "hola que tal"
    normalizado   = normalize_via_web(mensaje_crudo)

    _print_result("Prueba 38a: El servicio web normaliza correctamente el mensaje",
                    normalizado == esperado,
                    got=normalizado, expected=esperado)

    if normalizado:
        #Simular lo que hace client.py: normalizar y enviar
        code, mid = op_send(server, port, "alice", "bob", normalizado)
        _print_result("Prueba 38b: SEND con mensaje normalizado devuelve OK",
                        code == 0, got=code, expected=0)

        bob_got = cli_bob.wait_for_message()
        if bob_got:
            _, _, txt_recibido = cli_bob.received_messages[-1]
            _print_result("Prueba 38c: Bob recibe el mensaje normalizado (sin espacios repetidos)",
                            txt_recibido == esperado,
                            got=txt_recibido, expected=esperado)
        else:
            _print_result("Prueba 38c: Bob recibe el mensaje normalizado", False,
                            got="timeout sin mensaje")

    #Prueba 39: SENDATTACH con espacios repetidos en el mensaje
    tmp_src = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
    tmp_src.write(b"datos de prueba adjunto\n")
    tmp_src.close()

    msg_crudo_att = "mensaje   con   muchos   espacios"
    esperado_att = "mensaje con muchos espacios"
    norm_att = normalize_via_web(msg_crudo_att)

    _print_result("Prueba 39a: El servicio web normaliza el mensaje de SENDATTACH",
                    norm_att == esperado_att,
                    got=norm_att, expected=esperado_att)

    if norm_att:
        code2, mid2 = op_sendattach(server, port, "alice", "bob",
                                    norm_att, tmp_src.name)
        _print_result("Prueba 39b: SENDATTACH con mensaje normalizado devuelve OK",
                        code2 == 0, got=code2, expected=0)

        bob_got_att = cli_bob.wait_for_attachment()
        if bob_got_att:
            _, _, txt_att, fich_att = cli_bob.received_attachments[-1]
            _print_result("Prueba 39c: Bob recibe el mensaje con adjunto normalizado",
                            txt_att == esperado_att and fich_att == tmp_src.name,
                            got=(txt_att, fich_att),
                            expected=(esperado_att, tmp_src.name))
        else:
            _print_result("Prueba 39c: Bob recibe el mensaje con adjunto normalizado",
                            False, got="timeout sin mensaje")

    os.unlink(tmp_src.name)

    op_disconnect(server, port, "alice")
    op_disconnect(server, port, "bob")
    cli_alice.stop()
    cli_bob.stop()
    _cleanup(server, port, "alice", "bob")


#SUITE 5: SERVICIO RPC DE LOG (47-53)

def run_suite_rpc(server, port):
    _print_suite_header(
        "PRUEBAS DEL SERVICIO RPC DE LOG",
        "Pruebas 47-53: El servidor registra cada operacion via ONC-RPC en log_rpc_server"
    )

    rpc_bin = os.path.join(_WORKSPACE, 'log_rpc_server')
    server_bin = os.path.join(_WORKSPACE, 'server')
    rpc_srv_port = port + 1   #puerto separado para esta suite

    if not os.path.isfile(rpc_bin):
        print("[AVISO] No se encuentra ./log_rpc_server — omitiendo suite rpc.")
        return

    #Lanzar log_rpc_server capturando su stdout
    rpc_proc = subprocess.Popen(
        [rpc_bin],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=_WORKSPACE
    )
    time.sleep(1.0)   #esperar registro en portmapper

    #Hilo que acumula las lineas de log del servidor RPC
    rpc_lines = []
    rpc_lock  = threading.Lock()

    def _read_rpc():
        for line in rpc_proc.stdout:
            with rpc_lock:
                rpc_lines.append(line.rstrip('\n'))

    threading.Thread(target=_read_rpc, daemon=True).start()

    #Lanzar servidor de mensajeria con LOG_RPC_IP definido
    env = os.environ.copy()
    env['LOG_RPC_IP'] = '127.0.0.1'
    msg_proc = subprocess.Popen(
        [server_bin, '-p', str(rpc_srv_port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=_WORKSPACE
    )
    time.sleep(0.5)   #esperar arranque del servidor de mensajeria

    def _wait_log(expected, timeout=ASYNC_TIMEOUT):
        """Espera hasta que 'expected' aparezca como linea en el log RPC."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            with rpc_lock:
                if expected in rpc_lines:
                    return True
            time.sleep(0.1)
        return False

    try:
        _cleanup('127.0.0.1', rpc_srv_port, 'rpc_alice', 'rpc_bob')

        #Verifica que REGISTER y UNREGISTER quedan registrados en el servidor RPC.
        _print_block("BLOQUE 16 - RPC: REGISTER y UNREGISTER (pruebas 47-48)")

        #Prueba 47: REGISTER envia log RPC
        op_register('127.0.0.1', rpc_srv_port, 'rpc_alice')
        got = _wait_log('rpc_alice\tREGISTER')
        _print_result("Prueba 47: REGISTER queda registrado en log_rpc_server",
                        got, got="linea encontrada" if got else "timeout sin log")

        #Prueba 48: UNREGISTER envia log RPC
        op_unregister('127.0.0.1', rpc_srv_port, 'rpc_alice')
        got = _wait_log('rpc_alice\tUNREGISTER')
        _print_result("Prueba 48: UNREGISTER queda registrado en log_rpc_server",
                        got, got="linea encontrada" if got else "timeout sin log")

        #Verifica que CONNECT y DISCONNECT quedan registrados en el servidor RPC.
        _print_block("BLOQUE 17 - RPC: CONNECT y DISCONNECT (pruebas 49-50)")

        op_register('127.0.0.1', rpc_srv_port, 'rpc_alice')
        cli_a = SimulatedClient('127.0.0.1', rpc_srv_port, 'rpc_alice')
        cli_a.start()
        cli_a.connect_to_server()

        #Prueba 49: CONNECT envia log RPC
        got = _wait_log('rpc_alice\tCONNECT')
        _print_result("Prueba 49: CONNECT queda registrado en log_rpc_server",
                        got, got="linea encontrada" if got else "timeout sin log")

        #Prueba 50: DISCONNECT envia log RPC
        op_disconnect('127.0.0.1', rpc_srv_port, 'rpc_alice')
        cli_a.stop()
        got = _wait_log('rpc_alice\tDISCONNECT')
        _print_result("Prueba 50: DISCONNECT queda registrado en log_rpc_server",
                        got, got="linea encontrada" if got else "timeout sin log")

        #Verifica que SEND, USERS y SENDATTACH quedan registrados en el servidor RPC.
        _print_block("BLOQUE 18 - RPC: SEND, USERS y SENDATTACH (pruebas 51-53)")

        op_register('127.0.0.1', rpc_srv_port, 'rpc_bob')
        cli_a = SimulatedClient('127.0.0.1', rpc_srv_port, 'rpc_alice')
        cli_b = SimulatedClient('127.0.0.1', rpc_srv_port, 'rpc_bob')
        cli_a.start(); cli_b.start()
        cli_a.connect_to_server(); cli_b.connect_to_server()

        #Prueba 51: SEND envia log RPC
        op_send('127.0.0.1', rpc_srv_port, 'rpc_alice', 'rpc_bob', 'hola rpc')
        got = _wait_log('rpc_alice\tSEND')
        _print_result("Prueba 51: SEND queda registrado en log_rpc_server",
                        got, got="linea encontrada" if got else "timeout sin log")

        #Prueba 52: USERS envia log RPC
        op_users('127.0.0.1', rpc_srv_port, 'rpc_alice')
        got = _wait_log('rpc_alice\tUSERS')
        _print_result("Prueba 52: USERS queda registrado en log_rpc_server",
                        got, got="linea encontrada" if got else "timeout sin log")

        #Prueba 53: SENDATTACH envia log RPC con el nombre del fichero
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.txt')
        tmp.write(b'datos adjunto rpc\n')
        tmp.close()
        op_sendattach('127.0.0.1', rpc_srv_port, 'rpc_alice', 'rpc_bob',
                        'adjunto rpc', tmp.name)
        got = _wait_log('rpc_alice\tSENDATTACH\t' + tmp.name)
        _print_result("Prueba 53: SENDATTACH registrado en log_rpc_server con nombre de fichero",
                        got, got="linea encontrada" if got else "timeout sin log")
        os.unlink(tmp.name)

        cli_a.stop()
        cli_b.stop()
        _cleanup('127.0.0.1', rpc_srv_port, 'rpc_alice', 'rpc_bob')

    finally:
        msg_proc.terminate()
        try: msg_proc.wait(timeout=3)
        except Exception: msg_proc.kill()
        rpc_proc.terminate()
        try: rpc_proc.wait(timeout=3)
        except Exception: rpc_proc.kill()


#SUITE 6: PRUEBAS A TRAVES DE client.py (40-46)

def run_suite_cliente(server, port):
    _print_suite_header(
        "PRUEBAS A TRAVES DE client.py - Parte 3",
        "Pruebas 40-46: REGISTER, UNREGISTER, CONNECT, USERS, DISCONNECT y SEND usando client.py como subproceso"
    )

    def _run_client(commands, timeout=8.0):
        """Lanza client.py como subproceso, envia los comandos por stdin y devuelve stdout."""
        proc = subprocess.Popen(
            [sys.executable, 'client.py', '-s', server, '-p', str(port)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=_WORKSPACE
        )
        stdin_data = '\n'.join(commands) + '\n'
        try:
            out, _ = proc.communicate(input=stdin_data, timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, _ = proc.communicate()
        return out

    _cleanup(server, port, "cli_alice", "cli_alice2", "cli_bob")

    #Verifica REGISTER y UNREGISTER ejecutados desde client.py.
    _print_block("BLOQUE 13 - REGISTER y UNREGISTER via client.py (pruebas 40-42)")

    #rueba 40: REGISTER usuario nuevo via client.py
    out = _run_client(["REGISTER cli_alice2", "QUIT"])
    _print_result("Prueba 40: REGISTER usuario nuevo via client.py",
                    "c> REGISTER OK" in out, got=out.strip())

    # Prueba 41: REGISTER duplicado via client.py
    op_register(server, port, "cli_alice")
    out = _run_client(["REGISTER cli_alice", "QUIT"])
    _print_result("Prueba 41: REGISTER duplicado via client.py (USERNAME IN USE)",
                    "c> USERNAME IN USE" in out, got=out.strip())

    #Prueba 42: UNREGISTER via client.py
    out = _run_client(["UNREGISTER cli_alice2", "QUIT"])
    _print_result("Prueba 42: UNREGISTER via client.py",
                    "c> UNREGISTER OK" in out, got=out.strip())

    #Verifica CONNECT, USERS y DISCONNECT ejecutados desde client.py.
    _print_block("BLOQUE 14 - CONNECT, USERS y DISCONNECT via client.py (pruebas 43-45)")

    #Prueba 43: CONNECT via client.py
    out = _run_client(["CONNECT cli_alice", "DISCONNECT cli_alice", "QUIT"])
    _print_result("Prueba 43: CONNECT via client.py",
                    "c> CONNECT OK" in out, got=out.strip())

    #Prueba 44: USERS via client.py (mientras cli_alice esta conectada)
    out = _run_client(["CONNECT cli_alice", "USERS", "DISCONNECT cli_alice", "QUIT"])
    _print_result("Prueba 44: USERS via client.py",
                    "c> CONNECTED USERS" in out, got=out.strip())

    #Prueba 45: DISCONNECT via client.py
    _print_result("Prueba 45: DISCONNECT via client.py",
                    "c> DISCONNECT OK" in out, got=out.strip())

    _cleanup(server, port, "cli_alice", "cli_alice2")

    #Verifica SEND ejecutado desde client.py (requiere el servicio web activo).
    _print_block("BLOQUE 15 - SEND via client.py (prueba 46)")

    web_ok = False
    try:
        import urllib.request
        import json
        data = json.dumps({"message": "test"}).encode('utf-8')
        req = urllib.request.Request(
            'http://localhost:8000/normalize',
            data=data,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=2):
            web_ok = True
    except Exception:
        pass

    if not web_ok:
        print()
        print("[AVISO] El servicio web no responde en localhost:8000.")
        print("        Arrancalo con: python3 web/web_service.py")
        print("        La prueba 46 se omite.")
        return

    #Prueba 46: SEND via client.py con destinatario conectado
    op_register(server, port, "cli_alice")
    op_register(server, port, "cli_bob")
    cli_bob = SimulatedClient(server, port, "cli_bob")
    cli_bob.start()
    cli_bob.connect_to_server()

    out = _run_client(["CONNECT cli_alice", "SEND cli_bob hola mundo",
                        "DISCONNECT cli_alice", "QUIT"])
    _print_result("Prueba 46: SEND via client.py (web service activo, destinatario conectado)",
                    "c> SEND OK" in out, got=out.strip())

    cli_bob.stop()
    _cleanup(server, port, "cli_alice", "cli_bob")


#PUNTO DE ENTRADA

def main():
    parser = argparse.ArgumentParser(
        description="Script de pruebas automatizadas del servicio de mensajeria"
    )
    parser.add_argument('-s', type=str, required=True, metavar='IP',
                        help='IP del servidor de mensajeria')
    parser.add_argument('-p', type=int, required=True, metavar='PUERTO',
                        help='Puerto del servidor de mensajeria')
    parser.add_argument('--suite', type=str, default='all',
                        choices=['basica', 'pendientes', 'adjuntos', 'web', 'rpc', 'cliente', 'all'],
                        help='Suite de pruebas a ejecutar (por defecto: all)')
    args = parser.parse_args()

    print()
    print("Servidor: {}:{}".format(args.s, args.p))
    print("Suite:    {}".format(args.suite))

    if args.suite in ('basica', 'all'):
        run_suite_basica(args.s, args.p)

    if args.suite in ('pendientes', 'all'):
        run_suite_pendientes(args.s, args.p)

    if args.suite in ('adjuntos', 'all'):
        run_suite_adjuntos(args.s, args.p)

    if args.suite in ('web', 'all'):
        run_suite_web(args.s, args.p)

    if args.suite in ('rpc', 'all'):
        run_suite_rpc(args.s, args.p)

    if args.suite in ('cliente', 'all'):
        run_suite_cliente(args.s, args.p)

    _print_summary()


if __name__ == '__main__':
    main()
