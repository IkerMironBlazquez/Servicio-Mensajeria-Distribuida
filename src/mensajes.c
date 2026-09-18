#include <stdlib.h>
#include <string.h>
#include "include/mensajes.h"
#include "include/common.h"

/*
Reserva memoria para un nuevo nodo mensaje_t y rellena sus campos, los campos de cadena se copian con strncpy
Devuelve puntero al mensaje creado, o NULL si falla malloc
*/
mensaje_t *crear_mensaje(unsigned int id, const char *remitente, const char *destinatario,
    const char *texto, int tiene_adjunto, const char *fichero){
    mensaje_t *m = (mensaje_t *)malloc(sizeof(mensaje_t));
    if (m == NULL)
        return NULL; //fallo de asignación de memoria

    m->id = id;
    strncpy(m->remitente, remitente, MAX_USER - 1); 
    m->remitente[MAX_USER-1] = '\0';
    strncpy(m->destinatario, destinatario, MAX_USER - 1); 
    m->destinatario[MAX_USER-1] = '\0';
    strncpy(m->texto, texto, MAX_MESSAGE - 1); 
    m->texto[MAX_MESSAGE-1] = '\0';
    m->tiene_adjunto = tiene_adjunto;

    if (fichero != NULL)
        strncpy(m->fichero, fichero, MAX_FILENAME - 1);
    else
        m->fichero[0] = '\0';
    m->fichero[MAX_FILENAME - 1] = '\0';
    m->sig = NULL;

    return m;
}

/*
Añade msg al final de la lista *lista para mantener el orden de llegada
Devuelve 0 en éxito, -1 si msg o lista son NULL
*/
int agregar_mensaje(mensaje_t **lista, mensaje_t *msg){
    if (lista == NULL || msg == NULL)
        return -1;

    if (*lista == NULL) {
        *lista = msg; //lista vacía, el numero de mensaje el primero
        return 0;
    }

    //recorrer hasta el último nodo y enlazar al final
    mensaje_t *actual = *lista;
    while (actual->sig != NULL)
        actual = actual->sig;

    actual->sig = msg;
    msg->sig = NULL;

    return 0;
}

/*
Busca en *lista el mensaje con el id e remitente indicados y lo elimina, libera la memoria del nodo eliminado
Devuelve 0 si lo eliminó, -1 si no lo encontró
*/
int eliminar_mensaje_por_id_y_remitente(mensaje_t **lista, unsigned int id, const char *remitente){
    if (lista == NULL || *lista == NULL)
        return -1;

    mensaje_t *anterior = NULL;
    mensaje_t *actual   = *lista;

    while (actual != NULL) {
        if (actual->id == id && strcmp(actual->remitente, remitente) == 0) {
            //nodo encontrado: desenlazarlo
            if (anterior == NULL)
                *lista = actual->sig; //era el primer nodo
            else
                anterior->sig = actual->sig;
            free(actual);
            return 0;
        }
        anterior = actual;
        actual   = actual->sig;
    }

    return -1; //no encontrado
}

/*
Recorre la lista y libera la memoria de todos los nodos
*/
void liberar_mensajes(mensaje_t *lista){
    mensaje_t *actual = lista;
    while (actual != NULL) {
        mensaje_t *siguiente = actual->sig;
        free(actual);
        actual = siguiente;
    }
}
