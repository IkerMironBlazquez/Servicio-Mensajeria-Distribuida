from enum import Enum
import argparse
import socket
import threading
import sys

class client :

    # ******************** TYPES *********************
    # *
    # * @brief Return codes for the protocol methods
    class RC(Enum) :
        OK = 0
        ERROR = 1
        USER_ERROR = 2

    # ****************** ATTRIBUTES ******************
    _server = None
    _port = -1

    _current_user = None #nombre del usuario conectado
    _connected = False #True si hay un usuario conectado

    _listener_socket = None  #socket de escucha del hilo
    _listener_port = None #puerto en el que escucha el hilo
    _listener_thread = None  #objeto Thread del hilo
    _listener_running = False #flag para detener el hilo 

    #cache para guardar a los usuarios
    _connected_users_cache = {}

    #Envía la cadena text codificada en UTF-8 seguida del '\0'
    @staticmethod
    def _send_string(sock, text):
        data = text.encode('utf-8') + b'\x00'
        sock.sendall(data)

    #Recibe bytes del socket hasta encontrar '\0'
    #Devuelve la cadena decodificada, o None si se cierra la conexión
    @staticmethod
    def _recv_string(sock, max_len=4096):
        data = b""
        while len(data) < max_len:
            b = sock.recv(1)
            if not b:
                return None #conexión cerrada por el peer
            if b == b'\x00':
                return data.decode('utf-8', errors='replace')
            data += b
        return None # se superó el tamaño máximo sin encontrar '\0'

    #Envía un byte de código de respuesta
    @staticmethod
    def _send_code(sock, code):
        sock.sendall(bytes([code]))

    #Recibe un byte de código de respuesta
    #Devuelve el entero o None si se cierra la conexión
    @staticmethod
    def _recv_code(sock):
        data = sock.recv(1)
        if not data:
            return None
        return data[0]

    #Envía el contenido de un fichero local por el socket, primero envía el tamaño como cadena, luego los bytes
    #Si el fichero no existe o no se puede leer, envía -1.
    @staticmethod
    def _send_file_content(sock, path):
        try:
            with open(path, 'rb') as f:
                content = f.read()
            client._send_string(sock, str(len(content)))
            if len(content) > 0:
                sock.sendall(content)
        except OSError:
            client._send_string(sock, "-1") #fichero no disponible

    #Recibe el contenido de un fichero y lo guarda en local_path, recibe tamaño como cadena, luego los bytes.
    #Devuelve True en exito, False en error o tamaño -1.
    @staticmethod
    def _recv_file_content(sock, local_path):
        size_str = client._recv_string(sock)
        if size_str is None:
            return False
        size = int(size_str)
        if size < 0:
            return False #el remoto dio error
        
        #Recibir exactamente size bytes
        content = b""
        while len(content) < size:
            chunk = sock.recv(size - len(content))
            if not chunk:
                return False  #conexión cerrada antes de recibir todo
            content += chunk
        try:
            with open(local_path, 'wb') as f:
                f.write(content)
        except OSError:
            return False
        return True

    # ******************** METHODS *******************
    # *
    # * @param user - User name to register in the system
    # * 
    # * @return OK if successful
    # * @return USER_ERROR if the user is already registered
    # * @return ERROR if another error occurred
    @staticmethod
    def register(user):
        #Abre una conexión TCP al servidor, envía REGISTER y nombre de usuario
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((client._server, client._port))
            client._send_string(sock, "REGISTER")
            client._send_string(sock, user)
            code = client._recv_code(sock)
            sock.close()
        except Exception:
            print("c> REGISTER FAIL")
            return client.RC.ERROR

        if code == 0:
            print("c> REGISTER OK")
            return client.RC.OK
        elif code == 1:
            print("c> USERNAME IN USE")
            return client.RC.USER_ERROR
        else:
            print("c> REGISTER FAIL")
            return client.RC.ERROR

    # *
    # 	 * @param user - User name to unregister from the system
    # 	 * 
    # 	 * @return OK if successful
    # 	 * @return USER_ERROR if the user does not exist
    # 	 * @return ERROR if another error occurred
    @staticmethod
    def unregister(user):
        #Abre una conexión TCP al servidor, envía UNREGISTER  y nombre de usuario
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((client._server, client._port))
            client._send_string(sock, "UNREGISTER")
            client._send_string(sock, user)
            code = client._recv_code(sock)
            sock.close()
        except Exception:
            print("c> UNREGISTER FAIL")
            return client.RC.ERROR

        if code == 0:
            print("c> UNREGISTER OK")
            return client.RC.OK
        elif code == 1:
            print("c> USER DOES NOT EXIST")
            return client.RC.USER_ERROR
        else:
            print("c> UNREGISTER FAIL")
            return client.RC.ERROR


    #Detiene el hilo receptor cerrando el socket de escucha y esperando a que el hilo termine. 
    @staticmethod
    def _stop_listener():
        client._listener_running = False
        if client._listener_socket is not None:
            try:
                client._listener_socket.close()
            except Exception:
                pass
            client._listener_socket = None
        if client._listener_thread is not None:
            client._listener_thread.join(timeout=2.0)
            client._listener_thread = None
        client._listener_port = None

    #Bucle principal del hilo receptor, acepta conexiones entrantes del servidor y de otros clientes
    @staticmethod
    def _listener_loop():
        while client._listener_running:
            try:
                conn, _addr = client._listener_socket.accept()
            except OSError:
                break #socket cerrado desde _stop_listener

            try:
                op = client._recv_string(conn)
                if op is None:
                    continue

                if op == "SEND MESSAGE":
                    #Servidor entrega mensaje de texto
                    remitente = client._recv_string(conn)
                    msg_id = client._recv_string(conn)
                    texto = client._recv_string(conn)
                    print("\nc> MESSAGE " + msg_id + " FROM " + remitente + "\n" + texto + "\nEND")
                    sys.stdout.write("c> ")
                    sys.stdout.flush()

                elif op == "SEND MESS ACK":
                    #Servidor confirma que el mensaje fue entregado al destinatario
                    msg_id = client._recv_string(conn)
                    print("\nc> SEND MESSAGE " + msg_id + " OK")
                    sys.stdout.write("c> ")
                    sys.stdout.flush()

                elif op == "SEND MESSAGE ATTACH":
                    #Servidor entrega mensaje con adjunto
                    remitente = client._recv_string(conn)
                    msg_id = client._recv_string(conn)
                    texto = client._recv_string(conn)
                    fichero = client._recv_string(conn)
                    print("\nc> MESSAGE " + msg_id + " FROM " + remitente + "\n" + texto + "\nEND\nFILE " + fichero)
                    sys.stdout.write("c> ")
                    sys.stdout.flush()

                elif op == "SEND MESS ATTACH ACK":
                    #Servidor confirma que el mensaje con adjunto fue entregado
                    msg_id = client._recv_string(conn)
                    fichero = client._recv_string(conn)
                    print("\nc> SENDATTACH MESSAGE " + msg_id + " " + fichero + " OK")
                    sys.stdout.write("c> ")
                    sys.stdout.flush()

                elif op == "GET FILE":
                    #Otro cliente solicita un fichero
                    _solicitante = client._recv_string(conn)
                    fichero = client._recv_string(conn)
                    client._send_file_content(conn, fichero)

            except Exception:
                pass
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    @staticmethod
    def connect(user):
        #Si ya hay un usuario conectado localmente no se permite otra conexión
        if client._connected:
            print("c> USER ALREADY CONNECTED")
            return client.RC.USER_ERROR

        #Crear socket de escucha en un puerto libre
        try:
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(('', 0))
            listener.listen(5)
            port = listener.getsockname()[1]
        except Exception:
            print("c> CONNECT FAIL")
            return client.RC.ERROR

        client._listener_socket = listener
        client._listener_port = port
        client._listener_running = True

        #Lanzar el hilo receptor antes de enviar CONNECT al servidor
        t = threading.Thread(target=client._listener_loop, daemon=True)
        client._listener_thread = t
        t.start()

        #Enviar la operación CONNECT al servidor con el puerto de escucha
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((client._server, client._port))
            client._send_string(sock, "CONNECT")
            client._send_string(sock, user)
            client._send_string(sock, str(port))
            code = client._recv_code(sock)
            sock.close()
        except Exception:
            client._stop_listener()
            print("c> CONNECT FAIL")
            return client.RC.ERROR

        if code == 0:
            client._current_user = user
            client._connected = True
            print("c> CONNECT OK")
            return client.RC.OK
        else:
            client._stop_listener()
            if code == 1:
                print("c> CONNECT FAIL, USER DOES NOT EXIST")
                return client.RC.USER_ERROR
            elif code == 2:
                print("c> USER ALREADY CONNECTED")
                return client.RC.USER_ERROR
            else:
                print("c> CONNECT FAIL")
                return client.RC.ERROR

    # *
    # * 
    # * @return OK if successful
    # * @return USER_ERROR if the user does not exist or if it is already connected
    # * @return ERROR if another error occurred
    @staticmethod
    def  users() :
        #Verificar que hay un usuario conectado localmente
        if not client._connected or client._current_user is None:
            print("c> CONNECTED USERS FAIL, USER IS NOT CONNECTED")
            return client.RC.USER_ERROR

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((client._server, client._port))
            client._send_string(sock, "USERS")
            client._send_string(sock, client._current_user)
            code = client._recv_code(sock)

            if code == 0:
                num_str = client._recv_string(sock)
                num = int(num_str)
                entries = []
                for _ in range(num):
                    entry = client._recv_string(sock)
                    entries.append(entry)
                sock.close()

                print(f"c> CONNECTED USERS ({num} users connected) OK")
                for entry in entries:
                    print(entry)

                #Actualizar caché usuario ip, puerto para GETFILE
                for entry in entries:
                    parts = [p.strip() for p in entry.split("::")]
                    if len(parts) == 3:
                        client._connected_users_cache[parts[0]] = (parts[1], parts[2])

                return client.RC.OK

            elif code == 1:
                sock.close()
                print("c> CONNECTED USERS FAIL, USER IS NOT CONNECTED")
                return client.RC.USER_ERROR
            else:
                sock.close()
                print("c> CONNECTED USERS FAIL")
                return client.RC.ERROR

        except Exception:
            print("c> CONNECTED USERS FAIL")
            return client.RC.ERROR



    # *
    # * @param user - User name to disconnect from the system
    # * 
    # * @return OK if successful
    # * @return USER_ERROR if the user does not exist or is not connected
    # * @return ERROR if another error occurred
    @staticmethod
    def  disconnect(user) :
        #Envía DISCONNECT al servidor, muestra el resultado y siempre para el hilo receptor
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((client._server, client._port))
            client._send_string(sock, "DISCONNECT")
            client._send_string(sock, user)
            code = client._recv_code(sock)
            sock.close()
        except Exception:
            client._stop_listener()
            client._current_user = None
            client._connected = False
            print("c> DISCONNECT FAIL")
            return client.RC.ERROR

        #Parar el hilo receptor
        client._stop_listener()
        client._current_user = None
        client._connected = False

        if code == 0:
            print("c> DISCONNECT OK")
            return client.RC.OK
        elif code == 1:
            print("c> DISCONNECT FAIL, USER DOES NOT EXIST")
            return client.RC.USER_ERROR
        elif code == 2:
            print("c> DISCONNECT FAIL, USER NOT CONNECTED")
            return client.RC.USER_ERROR
        else:
            print("c> DISCONNECT FAIL")
            return client.RC.ERROR

    #Llama al servicio web local para normalizar el mensaje
    #Devuelve el mensaje normalizado, o None si el servicio no esta disponible
    @staticmethod
    def _normalize_message(text):
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
            return None  #servicio web no disponible

    # *
    # * @param user    - Receiver user name
    # * @param message - Message to be sent
    # *
    # * @return OK if the server had successfully delivered the message
    # * @return USER_ERROR if the user does not exist
    # * @return ERROR if another error occurred
    @staticmethod
    def send(user, message):
        #Si no hay usuario conectado no se puede construir el protocolo
        if not client._connected or client._current_user is None:
            print("c> SEND FAIL")
            return client.RC.ERROR

        #Normalizar el mensaje con el servicio web local antes de enviarlo
        normalized = client._normalize_message(message)
        if normalized is None:
            print("c> SEND FAIL")
            return client.RC.ERROR

        #Enviar la operacion SEND al servidor con remitente, destinatario y el mensaje
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((client._server, client._port))
            client._send_string(sock, "SEND")
            client._send_string(sock, client._current_user) #remitente
            client._send_string(sock, user) #destinatario
            client._send_string(sock, normalized)
            code = client._recv_code(sock)
            if code == 0:
                msg_id = client._recv_string(sock)
                sock.close()
                print("c> SEND OK - MESSAGE " + msg_id)
                return client.RC.OK
            elif code == 1:
                sock.close()
                print("c> SEND FAIL, USER DOES NOT EXIST")
                return client.RC.USER_ERROR
            else:
                sock.close()
                print("c> SEND FAIL")
                return client.RC.ERROR
        except Exception:
            print("c> SEND FAIL")
            return client.RC.ERROR

    # *
    # * @param user    - Receiver user name
    # * @param file    - file  to be sent
    # * @param message - Message to be sent
    # * 
    # * @return OK if the server had successfully delivered the message
    # * @return USER_ERROR if the user is not connected (the message is queued for delivery)
    # * @return ERROR the user does not exist or another error occurred
    @staticmethod
    def  sendAttach(user, message, file) :
        #Verificar que hay un usuario conectado
        if not client._connected or client._current_user is None:
            print("c> SENDATTACH FAIL")
            return client.RC.ERROR

        #Normalizar el mensaje con el servicio web local antes de enviarlo
        normalized = client._normalize_message(message)
        if normalized is None:
            print("c> SENDATTACH FAIL")
            return client.RC.ERROR

        #Enviar la operacion SENDATTACH al servidor con remitente, destinatario, mensaje y fichero
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((client._server, client._port))
            client._send_string(sock, "SENDATTACH")
            client._send_string(sock, client._current_user)  #remitente
            client._send_string(sock, user) #destinatario
            client._send_string(sock, normalized)
            client._send_string(sock, file)
            code = client._recv_code(sock)
            if code == 0:
                msg_id = client._recv_string(sock)
                sock.close()
                print("c> SENDATTACH OK - MESSAGE " + msg_id)
                return client.RC.OK
            elif code == 1:
                sock.close()
                print("c> SENDATTACH FAIL, USER DOES NOT EXIST")
                return client.RC.USER_ERROR
            else:
                sock.close()
                print("c> SENDATTACH FAIL")
                return client.RC.ERROR
        except Exception:
            print("c> SENDATTACH FAIL")
            return client.RC.ERROR

    #Método auxiliar para funcionalidad GETFILE
    @staticmethod
    def  getfile(user, filename, localfile) :
        #Verificar que hay un usuario conectado
        if not client._connected or client._current_user is None:
            print("c> FILE TRANSFER FAILED, user not connected.")
            return client.RC.ERROR

        #Buscar la IP y puerto del usuario remoto en la caché
        if user not in client._connected_users_cache:
            #Intentar refrescar la caché con una petición USERS al servidor
            client.users()

        if user not in client._connected_users_cache:
            print("c> FILE TRANSFER FAILED, user not connected.")
            return client.RC.ERROR

        remote_ip, remote_port = client._connected_users_cache[user]

        #Conectar directamente al hilo receptor del usuario y pedir el fichero
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((remote_ip, int(remote_port)))
            client._send_string(sock, "GET FILE")
            client._send_string(sock, client._current_user)
            client._send_string(sock, filename)

            #Recibir el contenido del fichero con el protocolo tamaño y bytes
            ok = client._recv_file_content(sock, localfile)
            sock.close()

            if ok:
                print("c> GETFILE OK")
                return client.RC.OK
            else:
                print("c> FILE TRANSFER FAILED")
                return client.RC.ERROR
        except Exception:
            print("c> FILE TRANSFER FAILED")
            return client.RC.ERROR

    # *
    # **
    # * @brief Command interpreter for the client. It calls the protocol functions.
    @staticmethod
    def shell():

        while (True) :
            try :
                command = input("c> ")
                line = command.split(" ")
                if (len(line) > 0):

                    line[0] = line[0].upper()

                    if (line[0]=="REGISTER") :
                        if (len(line) == 2) :
                            client.register(line[1])
                        else :
                            print("Syntax error. Usage: REGISTER <userName>")

                    elif(line[0]=="UNREGISTER") :
                        if (len(line) == 2) :
                            client.unregister(line[1])
                        else :
                            print("Syntax error. Usage: UNREGISTER <userName>")

                    elif(line[0]=="CONNECT") :
                        if (len(line) == 2) :
                            client.connect(line[1])
                        else :
                            print("Syntax error. Usage: CONNECT <userName>")

                    elif(line[0]=="DISCONNECT") :
                        if (len(line) == 2) :
                            client.disconnect(line[1])
                        else :
                            print("Syntax error. Usage: DISCONNECT <userName>")

                    elif(line[0]=="USERS") :
                        if (len(line) == 1) :
                            client.users()
                        else :
                            print("Syntax error. Usage: USERS")

                    elif(line[0]=="SEND") :
                        if (len(line) >= 3) :
                            #  Remove first two words
                            message = ' '.join(line[2:])
                            client.send(line[1], message)
                        else :
                            print("Syntax error. Usage: SEND <userName> <message>")

                    elif(line[0]=="SENDATTACH") :
                        if (len(line) >= 4) :
                            #destinatario en line[1], ficheroen ultimo token, mensaje en tokens intermedios
                            fichero = line[-1]
                            message = ' '.join(line[2:-1])
                            client.sendAttach(line[1], message, fichero)
                        else :
                            print("Syntax error. Usage: SENDATTACH <userName> <message> <fileName>")

                    elif(line[0]=="GETFILE") :
                        if (len(line) == 4) :
                            client.getfile(line[1], line[2], line[3])
                        else :
                            print("Syntax error. Usage: GETFILE <userName> <fileName> <localFileName>")

                    elif(line[0]=="QUIT") :
                        if (len(line) == 1) :
                            #Desconectar el usuario activo antes de salir
                            if client._connected and client._current_user is not None:
                                client.disconnect(client._current_user)
                            elif client._listener_running:
                                client._stop_listener()
                            break
                        else :
                            print("Syntax error. Use: QUIT")
                    else :
                        print("Error: command " + line[0] + " not valid.")
            except Exception as e:
                print("Exception: " + str(e))

    # *
    # * @brief Prints program usage
    @staticmethod
    def usage() :
        print("Usage: python3 client.py -s <server> -p <port>")


    # *
    # * @brief Parses program execution arguments
    @staticmethod
    def  parseArguments(argv) :
        parser = argparse.ArgumentParser()
        parser.add_argument('-s', type=str, required=True, help='Server IP')
        parser.add_argument('-p', type=int, required=True, help='Server Port')
        args = parser.parse_args()

        if (args.s is None):
            parser.error("Usage: python3 client.py -s <server> -p <port>")
            return False

        if ((args.p < 1024) or (args.p > 65535)):
            parser.error("Error: Port must be in the range 1024 <= port <= 65535");
            return False;
        
        client._server = args.s
        client._port   = args.p

        return True


    # ******************** MAIN *********************
    @staticmethod
    def main(argv) :
        if (not client.parseArguments(argv)) :
            client.usage()
            return

        client.shell()
        print("+++ FINISHED +++")
    

if __name__=="__main__":
    client.main(sys.argv[1:])
