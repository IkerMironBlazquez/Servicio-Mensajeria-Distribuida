#include <pthread.h>
#include <string.h>
#include <stdlib.h>
#include "include/servicio_mensajes.h"
#include "include/usuarios.h"
#include "include/mensajes.h"
#include "include/common.h"

//Lista global de usuarios y mutex que la protege
static usuario_t *usuarios = NULL;
static pthread_mutex_t mutex_servicio = PTHREAD_MUTEX_INITIALIZER;

/*
Inicializa el estado global del servicio
Debe llamarse una única vez al arrancar el servidor
*/
void servicio_init(void){
    pthread_mutex_lock(&mutex_servicio);
    usuarios = NULL;
    pthread_mutex_unlock(&mutex_servicio);
}

/*
Libera todos los usuarios y sus mensajes pendientes
Debe llamarse antes de terminar el servidor
*/
void servicio_destroy(void){
    pthread_mutex_lock(&mutex_servicio);
    liberar_usuarios(usuarios);
    usuarios = NULL;
    pthread_mutex_unlock(&mutex_servicio);
}

/*
Registra un nuevo usuario con el alias indicado
Bloquea el mutex, comprueba si ya existe y, si no, inserta el usuario
Devuelve SVC_OK, SVC_USER_EXISTS o SVC_ERROR
*/
int servicio_register(const char *username){
    pthread_mutex_lock(&mutex_servicio);

    //Comprobar si ya existe un usuario con ese nombre
    if (buscar_usuario(usuarios, username) != NULL) {
        pthread_mutex_unlock(&mutex_servicio);
        return SVC_USER_EXISTS;
    }

    //Intentar insertar el nuevo usuario en la lista
    if (insertar_usuario(&usuarios, username) != 0) {
        pthread_mutex_unlock(&mutex_servicio);
        return SVC_ERROR;
    }

    pthread_mutex_unlock(&mutex_servicio);
    return SVC_OK;
}

/*
Da de baja al usuario indicado y borra sus mensajes pendientes
Devuelve SVC_OK, SVC_USER_NOT_FOUND o SVC_ERROR
*/
int servicio_unregister(const char *username){
    pthread_mutex_lock(&mutex_servicio);

    //Comprobar si el usuario existe antes de intentar eliminarlo
    if (buscar_usuario(usuarios, username) == NULL) {
        pthread_mutex_unlock(&mutex_servicio);
        return SVC_USER_NOT_FOUND;
    }

    //Eliminar el usuario y sus mensajes pendientes
    if (eliminar_usuario(&usuarios, username) != 0) {
        pthread_mutex_unlock(&mutex_servicio);
        return SVC_ERROR;
    }

    pthread_mutex_unlock(&mutex_servicio);
    return SVC_OK;
}

/*
Conecta al usuario registrando su ip y puerto de escucha
Devuelve SVC_OK, SVC_USER_NOT_FOUND, SVC_ALREADY_CONNECTED o SVC_ERROR
*/
int servicio_connect(const char *username, const char *ip, const char *puerto){
    usuario_t *u;

    pthread_mutex_lock(&mutex_servicio);

    u = buscar_usuario(usuarios, username);
    if (u == NULL) {
        pthread_mutex_unlock(&mutex_servicio);
        return SVC_USER_NOT_FOUND;
    }

    if (u->conectado) {
        pthread_mutex_unlock(&mutex_servicio);
        return SVC_ALREADY_CONNECTED;
    }

    //Guardar ip y puerto y marcar como conectado
    marcar_conectado(u, ip, puerto);

    pthread_mutex_unlock(&mutex_servicio);
    return SVC_OK;
}

/*
Desconecta al usuario indicado verificando que la peticion viene de la IP desde la que se conecto
Devuelve SVC_OK, SVC_USER_NOT_FOUND, SVC_NOT_CONNECTED o SVC_ERROR
*/
int servicio_disconnect(const char *username, const char *client_ip){
    usuario_t *u;

    pthread_mutex_lock(&mutex_servicio);

    u = buscar_usuario(usuarios, username);
    if (u == NULL) {
        pthread_mutex_unlock(&mutex_servicio);
        return SVC_USER_NOT_FOUND;
    }

    if (!u->conectado) {
        pthread_mutex_unlock(&mutex_servicio);
        return SVC_NOT_CONNECTED;
    }

    //Verificar que la IP origen coincide con la IP activa del usuario
    if (strcmp(u->ip, client_ip) != 0) {
        pthread_mutex_unlock(&mutex_servicio);
        return SVC_ERROR;
    }

    //Limpiar IP, puerto y marcar como desconectado
    marcar_desconectado(u);

    pthread_mutex_unlock(&mutex_servicio);
    return SVC_OK;
}

/*
Crea un mensaje de texto de remitente a destinatario, lo añade a los pendientes del destinatario
Devuelve el id asignado y la info de conexion del destinatario antes de soltar el mutex
Devuelve SVC_OK, SVC_USER_NOT_FOUND o SVC_ERROR
*/
int servicio_send(const char *remitente, const char *destinatario, const char *texto,
    unsigned int *msg_id, int *dest_conectado, char *dest_ip, char *dest_puerto){
    usuario_t *u_rem;
    usuario_t *u_dest;
    mensaje_t *msg;

    pthread_mutex_lock(&mutex_servicio);

    //Buscar remitente y destinatario
    u_rem  = buscar_usuario(usuarios, remitente);
    u_dest = buscar_usuario(usuarios, destinatario);

    if (u_rem == NULL || u_dest == NULL) {
        pthread_mutex_unlock(&mutex_servicio);
        return SVC_USER_NOT_FOUND;
    }

    //Incrementar el id del remitente evitando desbordamiento a cero
    u_rem->ultimo_id++;
    if (u_rem->ultimo_id == 0)
        u_rem->ultimo_id = 1;

    //Crear el mensaje sin adjunto y añadirlo a los pendientes del destinatario
    msg = crear_mensaje(u_rem->ultimo_id, remitente, destinatario, texto, FALSE, NULL);
    if (msg == NULL) {
        pthread_mutex_unlock(&mutex_servicio);
        return SVC_ERROR;
    }

    if (agregar_mensaje(&u_dest->pendientes, msg) != 0) {
        free(msg);
        pthread_mutex_unlock(&mutex_servicio);
        return SVC_ERROR;
    }

    //Copiar id asignado y datos de conexion del destinatario antes de desbloquear
    *msg_id = u_rem->ultimo_id;
    *dest_conectado = u_dest->conectado;
    if (u_dest->conectado) {
        strncpy(dest_ip, u_dest->ip, MAX_IP - 1);
        dest_ip[MAX_IP - 1] = '\0';
        strncpy(dest_puerto, u_dest->puerto, MAX_PORT_STR - 1);
        dest_puerto[MAX_PORT_STR - 1] = '\0';
    }

    pthread_mutex_unlock(&mutex_servicio);
    return SVC_OK;
}

/*
Envía un mensaje con fichero adjunto, asigna un id al mensaje y lo devuelve en *msg_id
La lógica es identica a servicio_send pero el mensaje se guarda con tiene_adjunto=TRUE y el nombre del fichero
Devuelve la informacion de conexion del destinatario para entregar sin mantener el mutex
Devuelve SVC_OK, SVC_USER_NOT_FOUND o SVC_ERROR
*/
int servicio_sendattach(const char *remitente, const char *destinatario, const char *texto, const char *fichero, 
    unsigned int *msg_id, int *dest_conectado, char *dest_ip, char *dest_puerto){
    usuario_t *u_rem;
    usuario_t *u_dest;
    mensaje_t *msg;

    pthread_mutex_lock(&mutex_servicio);

    //Buscar remitente y destinatario
    u_rem = buscar_usuario(usuarios, remitente);
    u_dest = buscar_usuario(usuarios, destinatario);

    if (u_rem == NULL || u_dest == NULL) {
        pthread_mutex_unlock(&mutex_servicio);
        return SVC_USER_NOT_FOUND;
    }

    //Incrementar el id del remitente evitando desbordamiento a cero
    u_rem->ultimo_id++;
    if (u_rem->ultimo_id == 0){
        u_rem->ultimo_id = 1;
    }

    //Crear el mensaje con adjunto y añadirlo a los pendientes del destinatario
    msg = crear_mensaje(u_rem->ultimo_id, remitente, destinatario, texto, TRUE, fichero);
    if (msg == NULL) {
        pthread_mutex_unlock(&mutex_servicio);
        return SVC_ERROR;
    }

    if (agregar_mensaje(&u_dest->pendientes, msg) != 0) {
        free(msg);
        pthread_mutex_unlock(&mutex_servicio);
        return SVC_ERROR;
    }

    //Copiar id asignado y datos de conexion del destinatario antes de desbloquear
    *msg_id = u_rem->ultimo_id;
    *dest_conectado = u_dest->conectado;
    if (u_dest->conectado) {
        strncpy(dest_ip, u_dest->ip, MAX_IP - 1);
        dest_ip[MAX_IP - 1] = '\0';
        strncpy(dest_puerto, u_dest->puerto, MAX_PORT_STR - 1);
        dest_puerto[MAX_PORT_STR - 1] = '\0';
    }

    pthread_mutex_unlock(&mutex_servicio);
    return SVC_OK;
}

/*
Devuelve una lista de copias de los usuarios conectados junto con su IP y puerto, 
Si el solicitante no esta conectado devuelve SVC_NOT_CONNECTED
Si el solicitante no existe devuelve SVC_ERROR
En otro caso devuelve SVC_OK
*/
int servicio_users(const char *solicitante, usuario_t **lista_out, int *num_users){
    pthread_mutex_lock(&mutex_servicio);

    //Verificar que el solicitante existe y está conectado
    usuario_t *sol = buscar_usuario(usuarios, solicitante);
    if (sol == NULL) {
        pthread_mutex_unlock(&mutex_servicio);
        return SVC_ERROR;
    }
    if (!sol->conectado) {
        pthread_mutex_unlock(&mutex_servicio);
        return SVC_NOT_CONNECTED;
    }

    //Construir lista de copias superficiales de usuarios conectados (incluido el propio solicitante)
    usuario_t *copia = NULL;
    int count = 0;
    usuario_t *u = usuarios;
    while (u != NULL) {
        if (u->conectado) {
            usuario_t *nuevo = malloc(sizeof(usuario_t));
            if (nuevo == NULL) {
                liberar_usuarios(copia);
                pthread_mutex_unlock(&mutex_servicio);
                return SVC_ERROR;
            }
            strncpy(nuevo->nombre, u->nombre, MAX_USER - 1);
            nuevo->nombre[MAX_USER - 1] = '\0';
            strncpy(nuevo->ip, u->ip, MAX_IP - 1);
            nuevo->ip[MAX_IP - 1] = '\0';
            strncpy(nuevo->puerto, u->puerto, MAX_PORT_STR - 1);
            nuevo->puerto[MAX_PORT_STR - 1] = '\0';
            nuevo->conectado = 1;
            nuevo->ultimo_id = 0;
            nuevo->pendientes = NULL;
            nuevo->sig = copia;
            copia = nuevo;
            count++;
        }
        u = u->sig;
    }

    pthread_mutex_unlock(&mutex_servicio);
    *lista_out = copia;
    *num_users = count;
    return SVC_OK;
}

/*
Elimina de los pendientes del destinatario el mensaje con el id y remitente indicados
Se llama tras una entrega exitosa desde server.c
*/
void servicio_eliminar_pendiente(const char *destinatario, unsigned int msg_id, const char *remitente){
    pthread_mutex_lock(&mutex_servicio);
    usuario_t *u = buscar_usuario(usuarios, destinatario);
    if (u != NULL)
        eliminar_mensaje_por_id_y_remitente(&u->pendientes, msg_id, remitente);
    pthread_mutex_unlock(&mutex_servicio);
}

/*
Rellena los parametros de conexion actuales del usuario indicado si el usuario esta conectado
Devuelve 0 si el usuario existe, -1 si no existe
*/
int servicio_get_info_conexion(const char *username, int *conectado, char *ip_out, char *puerto_out){
    pthread_mutex_lock(&mutex_servicio);
    usuario_t *u = buscar_usuario(usuarios, username);
    if (u == NULL) {
        pthread_mutex_unlock(&mutex_servicio);
        return -1;
    }
    *conectado = u->conectado;
    if (u->conectado) {
        strncpy(ip_out, u->ip, MAX_IP - 1);
        ip_out[MAX_IP - 1] = '\0';
        strncpy(puerto_out, u->puerto, MAX_PORT_STR - 1);
        puerto_out[MAX_PORT_STR - 1] = '\0';
    }
    pthread_mutex_unlock(&mutex_servicio);
    return 0;
}

/*
Marca al usuario como desconectado sin verificar IP, usado cuando falla una entrega de mensaje
*/
void servicio_marcar_desconectado_forzado(const char *username){
    pthread_mutex_lock(&mutex_servicio);
    usuario_t *u = buscar_usuario(usuarios, username);
    if (u != NULL)
        marcar_desconectado(u);
    pthread_mutex_unlock(&mutex_servicio);
}

/*
Copia los campos del primer mensaje pendiente del usuario en los buffers de salida
Devuelve 0 si hay pendientes, -1 si la lista esta vacia o el usuario no existe
Permite iterar los pendientes desde server.c sin mantener el mutex durante la red
*/
int servicio_obtener_primer_pendiente(const char *username, unsigned int *id_out, char *remitente_out, char *texto_out, 
    int *tiene_adjunto_out, char *fichero_out){

    pthread_mutex_lock(&mutex_servicio);

    //Buscar al usuario; si no existe o no tiene pendientes, no hay nada que devolver
    usuario_t *u = buscar_usuario(usuarios, username);
    if (u == NULL || u->pendientes == NULL) {
        pthread_mutex_unlock(&mutex_servicio);
        return -1;
    }

    //Apuntar al primer mensaje de la lista de pendientes
    mensaje_t *m = u->pendientes;

    //Copiar los campos escalares directamente
    *id_out = m->id;
    *tiene_adjunto_out = m->tiene_adjunto;

    //Copiar los campos de cadena con limite para evitar desbordamiento de buffer
    strncpy(remitente_out, m->remitente, MAX_USER - 1);
    remitente_out[MAX_USER - 1] = '\0';
    strncpy(texto_out, m->texto, MAX_MESSAGE - 1);
    texto_out[MAX_MESSAGE - 1] = '\0';
    strncpy(fichero_out, m->fichero, MAX_FILENAME - 1);
    fichero_out[MAX_FILENAME - 1] = '\0';

    pthread_mutex_unlock(&mutex_servicio);
    return 0;
}
