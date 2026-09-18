#ifndef SERVICIO_MENSAJES_H
#define SERVICIO_MENSAJES_H

#include "usuarios.h"

/*
Inicializa el estado global del servicio, se llama al arrancar el servidor
*/
void servicio_init(void);

/*
Libera todo el estado global del servicio, se llama antes de terminar el servidor
*/
void servicio_destroy(void);

/*
Registra un nuevo usuario con el alias indicado
Devuelve SVC_OK, SVC_USER_EXISTS o SVC_ERROR
*/
int servicio_register(const char *username);

/*
Da de baja al usuario con el alias indicado
Devuelve SVC_OK, SVC_USER_NOT_FOUND o SVC_ERROR
*/
int servicio_unregister(const char *username);

/*
Conecta al usuario indicado registrando su ip y puerto
Devuelve SVC_OK, SVC_USER_NOT_FOUND, SVC_ALREADY_CONNECTED o SVC_ERROR
Si hay mensajes pendientes, los entrega al conectarse
*/
int servicio_connect(const char *username, const char *ip, const char *puerto);

/*
Desconecta al usuario indicado, verificando que la IP origen coincide con la IP activa
Devuelve SVC_OK, SVC_USER_NOT_FOUND, SVC_NOT_CONNECTED o SVC_ERROR
*/
int servicio_disconnect(const char *username, const char *client_ip);

/*
Crea un mensaje de texto de remitente a destinatario y lo añade a los pendientes del destinatario
Devuelve el id asignado en *msg_id y la info de conexion del destinatario para entrega sin mutex
Devuelve SVC_OK, SVC_USER_NOT_FOUND o SVC_ERROR
*/
int servicio_send(const char *remitente, const char *destinatario, const char *texto,
    unsigned int *msg_id, int *dest_conectado, char *dest_ip, char *dest_puerto);

/*
Envía un mensaje con fichero adjunto, asigna id al mensaje y lo devuelve en *msg_id
Devuelve la informacion de conexion del destinatario para entregar sin mantener el mutex
Devuelve SVC_OK, SVC_USER_NOT_FOUND o SVC_ERROR
*/
int servicio_sendattach(const char *remitente, const char *destinatario, const char *texto, const char *fichero, 
    unsigned int *msg_id, int *dest_conectado, char *dest_ip, char *dest_puerto);

/*
Rellena num_users con el número de usuarios conectados y devuelve una copia de la lista de usuarios
Devuelve SVC_OK, SVC_NOT_CONNECTED (si el solicitante no está conectado) o SVC_ERROR
*/
int servicio_users(const char *solicitante, usuario_t **lista_out, int *num_users);

/*
Elimina de los pendientes del destinatario el mensaje con el id y remitente indicados
Se llama tras una entrega exitosa desde server.c
*/
void servicio_eliminar_pendiente(const char *destinatario, unsigned int msg_id, const char *remitente);

/*
Rellena los parametros de conexion actuales del usuario indicado
Devuelve 0 si el usuario existe, -1 si no existe
*/
int servicio_get_info_conexion(const char *username, int *conectado, char *ip_out, char *puerto_out);

/*
Marca al usuario como desconectado sin verificar IP, usado cuando falla una entrega de mensaje
*/
void servicio_marcar_desconectado_forzado(const char *username);

/*
Copia los campos del primer mensaje pendiente del usuario en los buffers de salida
Devuelve 0 si hay pendientes, -1 si la lista esta vacia o el usuario no existe
Permite iterar los pendientes desde server.c sin mantener el mutex durante la red
*/
int servicio_obtener_primer_pendiente(const char *username, unsigned int *id_out,
    char *remitente_out, char *texto_out, int *tiene_adjunto_out, char *fichero_out);

#endif
