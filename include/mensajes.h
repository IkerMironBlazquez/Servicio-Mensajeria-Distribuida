#ifndef MENSAJES_H
#define MENSAJES_H

#include "common.h"

//Estructura del mensaje
typedef struct mensaje {
    unsigned int id; //identificador único del mensaje
    char remitente[MAX_USER]; // usuario que envía
    char destinatario[MAX_USER]; // usuario que recibe
    char texto[MAX_MESSAGE]; // texto del mensaje
    int  tiene_adjunto; // 0 = SEND, 1 = SENDATTACH
    char fichero[MAX_FILENAME]; // nombre del fichero adjunto
    struct mensaje *sig; // siguiente en la lista enlazada
} mensaje_t;


/*
Crea un nuevo mensaje con los campos indicados
Devuelve puntero al mensaje creado, o NULL si falla la asignación
*/
mensaje_t *crear_mensaje(unsigned int id, const char *remitente, const char *destinatario, 
    const char *texto, int tiene_adjunto, const char *fichero);

/*
Añade mensaje al final de la lista apuntada por *lista
Devuelve 0 en éxito, -1 en error
*/
int agregar_mensaje(mensaje_t **lista, mensaje_t *msg);

/*
Elimina de *lista el mensaje con el id e remitente indicados y libera la memoria del nodo 
Devuelve 0 si lo eliminó, -1 si no lo encontró
*/
int eliminar_mensaje_por_id_y_remitente(mensaje_t **lista, unsigned int id, const char *remitente);

/*
Libera todos los nodos de la lista de mensajes
*/
void liberar_mensajes(mensaje_t *lista);

#endif
