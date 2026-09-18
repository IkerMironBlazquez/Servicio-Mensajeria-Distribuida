#ifndef USUARIOS_H
#define USUARIOS_H

#include "common.h"
#include "mensajes.h"

//Estructura de usuario
typedef struct usuario {
    char nombre[MAX_USER]; //alias del usuario
    int  conectado; //1 = conectado, 0 = desconectado
    char ip[MAX_IP]; //IP activa (solo cuando conectado)
    char puerto[MAX_PORT_STR]; //puerto de escucha del hilo receptor
    unsigned int ultimo_id; //último id de mensaje asignado a este usuario
    mensaje_t *pendientes; //lista de mensajes pendientes de entrega
    struct usuario *sig; //siguiente en la lista enlazada
} usuario_t;


/*
Busca un usuario por nombre en la lista
Devuelve puntero al usuario, o NULL si no existe
*/
usuario_t *buscar_usuario(usuario_t *lista, const char *nombre);

/*
Inserta un nuevo usuario con el nombre indicado al inicio de la lista
Devuelve 0 en éxito, -1 si ya existe o falla la asignacion
*/
int insertar_usuario(usuario_t **lista, const char *nombre);

/*
Elimina el usuario con el nombre indicado de la lista y libera sus mensajes pendientes
Devuelve 0 en éxito, -1 si no existe
*/
int eliminar_usuario(usuario_t **lista, const char *nombre);

/*
Libera todos los usuarios y sus mensajes pendientes
*/
void liberar_usuarios(usuario_t *lista);

/*
Marca al usuario como conectado, guardando ip y puerto
*/
void marcar_conectado(usuario_t *u, const char *ip, const char *puerto);

/*
Marca al usuario como desconectado y borra su ip/puerto
*/
void marcar_desconectado(usuario_t *u);

#endif
