#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <signal.h>
#include <pthread.h>
#include <arpa/inet.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <netdb.h>
#include "include/common.h"
#include "include/protocolo.h"
#include "include/servicio_mensajes.h"
#include "include/log_rpc_client.h"

//Estructura pasada a cada hilo de atención al cliente
typedef struct {
    int  sock; //socket aceptado
    char ip[MAX_IP]; //IP del cliente remoto (obtenida de accept)
} thread_arg_t;

//Declaraciones de los manejadores de operaciones
void handle_register(int sock);
void handle_unregister(int sock);
void handle_connect(int sock, const char *client_ip);
void handle_disconnect(int sock, const char *client_ip);
void handle_send(int sock);
void handle_sendattach(int sock);
void handle_users(int sock);

//Declaración del hilo de atención
void *handle_client(void *arg);

//Funcion auxiliar para entregar un mensaje al hilo receptor de un cliente
static void entregar_mensaje(unsigned int id, const char *remitente, const char *destinatario, const char *texto, 
    int tiene_adjunto, const char *fichero, const char *dest_ip, const char *dest_puerto);

//Variable para controlar la terminación del bucle principal
static volatile sig_atomic_t seguir = 1;

//Funcion para terminar
static void sigint_handler(int sig){
    (void)sig;
    seguir = 0;
}

/*
Punto de entrada del servidor
Parsea el puerto, crea el socket TCP, hace bind/listen e inicia el bucle de accept lanzando un hilo por cada conexion
Al recibir SIGINT termina limpiamente liberando todos los recursos
*/
int main(int argc, char *argv[]){
    int sd; //socket servidor
    int puerto = -1; //puerto de escucha
    int opt = 1; //opcion SO_REUSEADDR
    struct sockaddr_in server_addr; //direccion local del servidor
    struct sockaddr_in client_addr; //direccion del cliente aceptado
    socklen_t client_len;
    char local_ip[MAX_IP]; //IP local para el mensaje de inicio
    pthread_t th; //identificador de hilo (no se usa tras detach)
    pthread_attr_t attr; //atributos de los hilos

    //Parsear argumentos, ./server -p <puerto>
    for (int i = 1; i < argc - 1; i++) {
        if (strcmp(argv[i], "-p") == 0) {
            puerto = atoi(argv[i + 1]);
            break;
        }
    }

    if (puerto < 1 || puerto > 65535) {
        fprintf(stderr, "Uso: %s -p <puerto>\n", argv[0]);
        return -1;
    }

    //Instalar manejador de señal SIGINT
    signal(SIGINT, sigint_handler);

    //Inicializar la logica del servicio de mensajeria
    servicio_init();

    //Inicializar el cliente RPC 
    log_rpc_init();

    //Crear socket TCP
    sd = socket(AF_INET, SOCK_STREAM, 0);
    if (sd < 0) {
        perror("socket");
        servicio_destroy();
        log_rpc_destroy();
        return -1;
    }

    //Reutilizacion del puerto para reiniciar rapido tras caida
    if (setsockopt(sd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt)) < 0) {
        perror("setsockopt");
        close(sd);
        servicio_destroy();
        log_rpc_destroy();
        return -1;
    }

    //Preparar direccion local del servidor (escucha en todas las interfaces)
    memset(&server_addr, 0, sizeof(server_addr));
    server_addr.sin_family      = AF_INET;
    server_addr.sin_addr.s_addr = INADDR_ANY;
    server_addr.sin_port        = htons((uint16_t)puerto);

    //Bind
    if (bind(sd, (struct sockaddr *)&server_addr, sizeof(server_addr)) < 0) {
        perror("bind");
        close(sd);
        servicio_destroy();
        log_rpc_destroy();
        return -1;
    }

    //Listen
    if (listen(sd, SOMAXCONN) < 0) {
        perror("listen");
        close(sd);
        servicio_destroy();
        log_rpc_destroy();
        return -1;
    }

    char hostname[256];
    struct addrinfo hints, *res;
    if (gethostname(hostname, sizeof(hostname)) == 0) {
        memset(&hints, 0, sizeof(hints));
        hints.ai_family = AF_INET;

        if (getaddrinfo(hostname, NULL, &hints, &res) == 0) {
            inet_ntop(AF_INET,
                        &((struct sockaddr_in *)res->ai_addr)->sin_addr, local_ip, sizeof(local_ip));
            freeaddrinfo(res);

        } 
        else {
            strncpy(local_ip, "0.0.0.0", sizeof(local_ip) - 1);
            local_ip[sizeof(local_ip) - 1] = '\0';
        }

    } 
    else {
        strncpy(local_ip, "0.0.0.0", sizeof(local_ip) - 1);
        local_ip[sizeof(local_ip) - 1] = '\0';
    }

    printf("s> init server %s:%d\n", local_ip, puerto);
    printf("s> \n");
    fflush(stdout);

    //Configurar hilos como detached: no necesitamos hacer join
    if (pthread_attr_init(&attr) != 0) {
        close(sd);
        servicio_destroy();
        log_rpc_destroy();
        return -1;
    }
    if (pthread_attr_setdetachstate(&attr, PTHREAD_CREATE_DETACHED) != 0) {
        pthread_attr_destroy(&attr);
        close(sd);
        servicio_destroy();
        log_rpc_destroy();
        return -1;
    }

    //Bucle de aceptacion de conexiones entrantes
    while (seguir) {
        client_len = sizeof(client_addr);

        //Reservar estructura de argumento para el nuevo hilo
        thread_arg_t *targ = malloc(sizeof(thread_arg_t));
        if (targ == NULL)
            continue; //sin memoria; intentar en la siguiente iteracion

        //Esperar hasta que llegue un cliente
        targ->sock = accept(sd, (struct sockaddr *)&client_addr, &client_len);
        if (targ->sock < 0) {
            free(targ);
            if (!seguir)
                break; //SIGINT interrumpio el accept, salir del bucle
            continue;
        }

        //Guardar la IP remota del cliente (para CONNECT y DISCONNECT)
        inet_ntop(AF_INET, &client_addr.sin_addr, targ->ip, sizeof(targ->ip));

        //Crear hilo para atender esta conexion
        if (pthread_create(&th, &attr, handle_client, targ) != 0) {
            close(targ->sock);
            free(targ);
            continue;
        }
    }

    pthread_attr_destroy(&attr);
    close(sd);
    servicio_destroy();
    log_rpc_destroy();
    return 0;
}


/*
Maneja la operacion REGISTER
Lee el nombre de usuario, invoca la logica del servicio y responde con el codigo de protocolo correspondiente. 
Registra la operacion en el servidor RPC.
*/
void handle_register(int sock){
    char username[MAX_USER];
    int ret;

    //Leer el nombre de usuario enviado por el cliente
    if (recv_string(sock, username, sizeof(username)) < 0) {
        send_code(sock, PROTO_ERR2);
        return;
    }

    //Registrar la operacion en el servidor RPC
    log_rpc_log(username, OP_REGISTER, NULL);

    //Ejecutar la logica del servicio
    ret = servicio_register(username);

    if (ret == SVC_OK) {
        send_code(sock, PROTO_OK);
        printf("s> REGISTER %s OK\n", username);
    } else if (ret == SVC_USER_EXISTS) {
        send_code(sock, PROTO_ERR1);
        printf("s> REGISTER %s FAIL\n", username);
    } else {
        send_code(sock, PROTO_ERR2);
        printf("s> REGISTER %s FAIL\n", username);
    }
    fflush(stdout);
}

/*
Operacion UNREGISTER.
Lee el nombre de usuario, invoca la logica del servicio y responde con el codigode protocolo correspondiente
*/
void handle_unregister(int sock){
    char username[MAX_USER];
    int ret;

    //Leer el nombre de usuario enviado por el cliente
    if (recv_string(sock, username, sizeof(username)) < 0) {
        send_code(sock, PROTO_ERR2);
        return;
    }

    //Registrar la operacion en el servidor RPC
    log_rpc_log(username, OP_UNREGISTER, NULL);

    //Ejecutar la logica del servicio
    ret = servicio_unregister(username);

    if (ret == SVC_OK) {
        send_code(sock, PROTO_OK);
        printf("s> UNREGISTER %s OK\n", username);
    } else if (ret == SVC_USER_NOT_FOUND) {
        send_code(sock, PROTO_ERR1);
        printf("s> UNREGISTER %s FAIL\n", username);
    } else {
        send_code(sock, PROTO_ERR2);
        printf("s> UNREGISTER %s FAIL\n", username);
    }
    fflush(stdout);
}

/*
Operacion CONNECT
Lee nombre de usuario y puerto de escucha, invoca la logica del servicio y responde con el codigo de protocolo 
Si el usuario se conecta correctamente, entrega sus mensajes pendientes
Registra la operacion en el servidor RPC
*/
void handle_connect(int sock, const char *client_ip){
    char username[MAX_USER];
    char puerto[MAX_PORT_STR];
    int ret;

    //Leer nombre de usuario y puerto de escucha del hilo receptor del cliente
    if (recv_string(sock, username, sizeof(username)) < 0) {
        send_code(sock, PROTO_ERR3);
        return;
    }
    if (recv_string(sock, puerto, sizeof(puerto)) < 0) {
        send_code(sock, PROTO_ERR3);
        return;
    }

    //Registrar la operacion en el servidor RPC
    log_rpc_log(username, OP_CONNECT, NULL);

    //Ejecutar la logica del servicio, la IP viene de accept, no del cliente
    ret = servicio_connect(username, client_ip, puerto);

    if (ret == SVC_OK) {
        send_code(sock, PROTO_OK);
        printf("s> CONNECT %s OK\n", username);
        fflush(stdout);

        /* Fase 11: entregar mensajes pendientes al recien conectado */
        {
            char pm_remitente[MAX_USER], pm_texto[MAX_MESSAGE], pm_fichero[MAX_FILENAME];
            char pm_ip[MAX_IP], pm_puerto[MAX_PORT_STR];
            unsigned int pm_id;
            int pm_tiene_adjunto, pm_conectado = 0;

            // La IP y puerto ya fueron registrados por servicio_connect
            servicio_get_info_conexion(username, &pm_conectado, pm_ip, pm_puerto);

            // Intentar entregar cada pendiente; si falla, el usuario queda desconectado y paramos
            while (pm_conectado && servicio_obtener_primer_pendiente(username, &pm_id, pm_remitente, pm_texto, &pm_tiene_adjunto, pm_fichero) == 0) {
                entregar_mensaje(pm_id, pm_remitente, username, pm_texto, pm_tiene_adjunto, pm_fichero, pm_ip, pm_puerto);
                // Comprobar si el usuario sigue conectado tras el intento
                servicio_get_info_conexion(username, &pm_conectado, pm_ip, pm_puerto);
            }
        }
    } else if (ret == SVC_USER_NOT_FOUND) {
        send_code(sock, PROTO_ERR1);
        printf("s> CONNECT %s FAIL\n", username);
        fflush(stdout);
    } else if (ret == SVC_ALREADY_CONNECTED) {
        send_code(sock, PROTO_ERR2);
        printf("s> CONNECT %s FAIL\n", username);
        fflush(stdout);
    } else {
        send_code(sock, PROTO_ERR3);
        printf("s> CONNECT %s FAIL\n", username);
        fflush(stdout);
    }
}

/*
Operacion DISCONNECT
Lee el nombre de usuario, verifica que la peticion viene de la IP activa del usuario y responde con el codigo de protocolo correspondiente
Registra la operacion en el servidor RPC
*/
void handle_disconnect(int sock, const char *client_ip){
    char username[MAX_USER];
    int ret;

    //Leer el nombre de usuario enviado por el cliente
    if (recv_string(sock, username, sizeof(username)) < 0) {
        send_code(sock, PROTO_ERR3);
        return;
    }

    //Registrar la operacion en el servidor RPC
    log_rpc_log(username, OP_DISCONNECT, NULL);

    //Ejecutar la logica del servicio, verificando la IP origen
    ret = servicio_disconnect(username, client_ip);

    if (ret == SVC_OK) {
        send_code(sock, PROTO_OK);
        printf("s> DISCONNECT %s OK\n", username);
    } 
    else if (ret == SVC_USER_NOT_FOUND) {
        send_code(sock, PROTO_ERR1);
        printf("s> DISCONNECT %s FAIL\n", username);
    } 
    else if (ret == SVC_NOT_CONNECTED) {
        send_code(sock, PROTO_ERR2);
        printf("s> DISCONNECT %s FAIL\n", username);
    } 
    else {
        send_code(sock, PROTO_ERR3);
        printf("s> DISCONNECT %s FAIL\n", username);
    }
    fflush(stdout);
}

/*
Conecta al hilo receptor del cliente en dest_ip:dest_puerto y entrega el mensaje
Si la entrega tiene exito, elimina el mensaje de pendientes del destinatario y envia ACK al remitente
Si la entrega falla, conserva el mensaje pendiente y marca al destinatario como desconectado
*/
static void entregar_mensaje(unsigned int id, const char *remitente, const char *destinatario, const char *texto, 
    int tiene_adjunto, const char *fichero, const char *dest_ip, const char *dest_puerto){
    struct addrinfo hints, *res;
    int sock;
    char id_str[MAX_ID_STR];
    int entregado = 0;

    snprintf(id_str, sizeof(id_str), "%u", id);

    //Intentar conectar al hilo receptor del destinatario
    memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;

    if (getaddrinfo(dest_ip, dest_puerto, &hints, &res) == 0) {
        sock = socket(res->ai_family, res->ai_socktype, res->ai_protocol);
        if (sock >= 0) {
            if (connect(sock, res->ai_addr, res->ai_addrlen) == 0) {
                //Enviar el mensaje segun si tiene adjunto o no
                int correcto;
                if (!tiene_adjunto) {
                    correcto = (send_string(sock, OP_SEND_MSG) >= 0  && send_string(sock, remitente) >= 0  
                    && send_string(sock, id_str) >= 0  && send_string(sock, texto) >= 0);
                } 
                else {
                    correcto = (send_string(sock, OP_SEND_MSG_ATT) >= 0  && send_string(sock, remitente) >= 0  && send_string(sock, id_str) >= 0  &&
                            send_string(sock, texto) >= 0  && send_string(sock, fichero) >= 0);
                }
                if (correcto){
                    entregado = 1;
                } 
            }
            close(sock);
        }
        freeaddrinfo(res);
    }

    if (entregado) {
        //Entrega exitosa, eliminar de pendientes y loguear
        servicio_eliminar_pendiente(destinatario, id, remitente);
        printf("s> SEND MESSAGE %u FROM %s TO %s\n", id, remitente, destinatario);
        fflush(stdout);

        //Enviar ACK al remitente si sigue conectado
        int rem_conectado = 0;
        char rem_ip[MAX_IP] = {0};
        char rem_puerto[MAX_PORT_STR] = {0};

        //Consultar si el remitente sigue conectado y obtener su IP y puerto de escucha
        if (servicio_get_info_conexion(remitente, &rem_conectado, rem_ip, rem_puerto) == 0 && rem_conectado) {
            memset(&hints, 0, sizeof(hints));
            hints.ai_family   = AF_INET;
            hints.ai_socktype = SOCK_STREAM;

            //Resolver la dirección del hilo receptor del remitente
            if (getaddrinfo(rem_ip, rem_puerto, &hints, &res) == 0) {
                int ack_sock = socket(res->ai_family, res->ai_socktype, res->ai_protocol);
                if (ack_sock >= 0) {
                    //Conectar al hilo receptor del remitente y enviarle el ACK
                    if (connect(ack_sock, res->ai_addr, res->ai_addrlen) == 0) {
                        if (!tiene_adjunto) {
                            //ACK simple: solo se envía el id del mensaje
                            send_string(ack_sock, OP_SEND_ACK);
                            send_string(ack_sock, id_str);
                        } else {
                            //ACK con adjunto: se envía también el nombre del fichero
                            send_string(ack_sock, OP_SEND_ACK_ATT);
                            send_string(ack_sock, id_str);
                            if (fichero != NULL)
                                send_string(ack_sock, fichero);
                        }
                    }
                    close(ack_sock);
                }
                freeaddrinfo(res);
            }
        }
    } else {
        //Fallo de entrega, conservar pendiente y marcar destinatario como desconectado
        servicio_marcar_desconectado_forzado(destinatario);
        printf("s> MESSAGE %u FROM %s TO %s STORED\n", id, remitente, destinatario);
        fflush(stdout);
    }
}

/*
Operacion SEND
Lee remitente, destinatario y mensaje, ejecuta la logica del servicio y responde con codigo y la id del mensaje
Registra la operacion en el servidor RPC
*/
void handle_send(int sock){
    char remitente[MAX_USER];
    char destinatario[MAX_USER];
    char texto[MAX_MESSAGE];
    unsigned int msg_id = 0;
    int dest_conectado = 0;
    char dest_ip[MAX_IP] = {0};
    char dest_puerto[MAX_PORT_STR] = {0};
    char id_str[MAX_ID_STR];
    int ret;

    //Leer remitente, destinatario y mensaje enviados por el cliente
    if (recv_string(sock, remitente, sizeof(remitente)) < 0) {
        send_code(sock, PROTO_ERR2);
        return;
    }
    if (recv_string(sock, destinatario, sizeof(destinatario)) < 0) {
        send_code(sock, PROTO_ERR2);
        return;
    }
    if (recv_string(sock, texto, sizeof(texto)) < 0) {
        send_code(sock, PROTO_ERR2);
        return;
    }

    //Registrar la operacion en el servidor RPC
    log_rpc_log(remitente, OP_SEND, NULL);

    //Ejecutar la logica del servicio
    ret = servicio_send(remitente, destinatario, texto, &msg_id, &dest_conectado, dest_ip, dest_puerto);

    if (ret == SVC_USER_NOT_FOUND) {
        send_code(sock, PROTO_ERR1);
        return;
    } 
    else if (ret != SVC_OK) {
        send_code(sock, PROTO_ERR2);
        return;
    }

    //Responder al cliente con codigo 0 y el id asignado al mensaje
    snprintf(id_str, sizeof(id_str), "%u", msg_id);
    send_code(sock, PROTO_OK);
    send_string(sock, id_str);

    //Intentar entregar al destinatario conectado o loguear como pendiente
    if (dest_conectado) {
        entregar_mensaje(msg_id, remitente, destinatario, texto, FALSE, NULL, dest_ip, dest_puerto);
    } else {
        printf("s> MESSAGE %u FROM %s TO %s STORED\n", msg_id, remitente, destinatario);
        fflush(stdout);
    }
}

/*
Operacion SENDATTACH
Lee remitente, destinatario, mensaje y nombre de fichero, ejecuta la logica del servicio y responde
Registra la operacion en el servidor RPC incluyendo el nombre del fichero
*/
void handle_sendattach(int sock){
    char remitente[MAX_USER];
    char destinatario[MAX_USER];
    char texto[MAX_MESSAGE];
    char fichero[MAX_FILENAME];
    unsigned int msg_id = 0;
    int dest_conectado = 0;
    char dest_ip[MAX_IP] = {0};
    char dest_puerto[MAX_PORT_STR] = {0};
    char id_str[MAX_ID_STR];
    int ret;

    //Leer remitente, destinatario, mensaje y nombre de fichero
    if (recv_string(sock, remitente, sizeof(remitente)) < 0) {
        send_code(sock, PROTO_ERR2);
        return;
    }
    if (recv_string(sock, destinatario, sizeof(destinatario)) < 0) {
        send_code(sock, PROTO_ERR2);
        return;
    }
    if (recv_string(sock, texto, sizeof(texto)) < 0) {
        send_code(sock, PROTO_ERR2);
        return;
    }
    if (recv_string(sock, fichero, sizeof(fichero)) < 0) {
        send_code(sock, PROTO_ERR2);
        return;
    }

    //Registrar la operacion en el servidor RPC incluyendo el nombre del fichero
    log_rpc_log(remitente, OP_SENDATTACH, fichero);

    //Ejecutar la logica del servicio
    ret = servicio_sendattach(remitente, destinatario, texto, fichero,
                                &msg_id, &dest_conectado, dest_ip, dest_puerto);

    if (ret == SVC_USER_NOT_FOUND) {
        send_code(sock, PROTO_ERR1);
        return;
    }
    else if (ret != SVC_OK) {
        send_code(sock, PROTO_ERR2);
        return;
    }

    //Responder al cliente con codigo 0 y el id asignado al mensaje
    snprintf(id_str, sizeof(id_str), "%u", msg_id);
    send_code(sock, PROTO_OK);
    send_string(sock, id_str);

    //Intentar entregar al destinatario conectado o loguear como pendiente
    if (dest_conectado) {
        entregar_mensaje(msg_id, remitente, destinatario, texto, TRUE, fichero, dest_ip, dest_puerto);
    } else {
        printf("s> MESSAGE %u FROM %s TO %s STORED\n", msg_id, remitente, destinatario);
        fflush(stdout);
    }
}

/*
Lee el usuario solicitante, llama a servicio_users y responde con la lista de usuarios conectados
Cada usuario se envía como "nombre :: IP :: puerto", el solicitante SÍ aparece en la lista si está conectado
*/
void handle_users(int sock){
    char username[MAX_USER];

    //Leer el usuario que pide la lista (necesario para verificar que está conectado)
    if (recv_string(sock, username, sizeof(username)) < 0)
        return;

    log_rpc_log(username, OP_USERS, NULL);

    usuario_t *lista = NULL;
    int num = 0;
    int ret = servicio_users(username, &lista, &num);

    if (ret == SVC_OK) {
        char num_str[MAX_ID_STR];
        snprintf(num_str, sizeof(num_str), "%d", num);
        send_code(sock, PROTO_OK);
        send_string(sock, num_str);

        //Enviar cada usuario como "nombre :: IP :: puerto"
        usuario_t *u = lista;
        while (u != NULL) {
            char entrada[MAX_USER + MAX_IP + MAX_PORT_STR + 16];
            snprintf(entrada, sizeof(entrada), "%s :: %s :: %s", u->nombre, u->ip, u->puerto);
            send_string(sock, entrada);
            u = u->sig;
        }
        liberar_usuarios(lista);

        printf("s> CONNECTEDUSERS OK\n");
        fflush(stdout);
    } 
    else if (ret == SVC_NOT_CONNECTED) {
        send_code(sock, PROTO_ERR1);
        printf("s> CONNECTEDUSERS FAIL\n");
        fflush(stdout);
    } 
    else {
        send_code(sock, PROTO_ERR2);
        printf("s> CONNECTEDUSERS FAIL\n");
        fflush(stdout);
    }
}

/*
Lee la operacion enviada como cadena terminada en '\0', la compara con las operaciones conocidas y llama al manejador
correspondiente. Si la operacion es desconocida, cierra sin modificar el estado del servicio
*/
void *handle_client(void *arg){
    thread_arg_t *targ = (thread_arg_t *)arg;
    char operacion[MAX_OP];

    //Leer la operacion enviada por el cliente
    if (recv_string(targ->sock, operacion, sizeof(operacion)) < 0) {
        close(targ->sock);
        free(targ);
        return NULL;
    }

    //Elegir segun la operacion recibida
    if (strcmp(operacion, OP_REGISTER) == 0) {
        handle_register(targ->sock);
    } 
    else if (strcmp(operacion, OP_UNREGISTER) == 0) {
        handle_unregister(targ->sock);
    } 
    else if (strcmp(operacion, OP_CONNECT) == 0) {
        handle_connect(targ->sock, targ->ip);
    } 
    else if (strcmp(operacion, OP_DISCONNECT) == 0) {
        handle_disconnect(targ->sock, targ->ip);
    } 
    else if (strcmp(operacion, OP_SEND) == 0) {
        handle_send(targ->sock);
    } 
    else if (strcmp(operacion, OP_SENDATTACH) == 0) {
        handle_sendattach(targ->sock);
    } 
    else if (strcmp(operacion, OP_USERS) == 0) {
        handle_users(targ->sock);
    }
    //Operacion desconocida, cerrar sin modificar estado

    close(targ->sock);
    free(targ);
    return NULL;
}

