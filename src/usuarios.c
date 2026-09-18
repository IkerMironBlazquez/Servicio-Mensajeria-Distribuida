#include <stdlib.h>
#include <string.h>
#include "include/usuarios.h"
#include "include/mensajes.h"
#include "include/common.h"

/*
Recorre la lista enlazada y devuelve el puntero al usuario cuyo nombre
coinside con el parámetro, o NULL si no existe.
*/
usuario_t *buscar_usuario(usuario_t *lista, const char *nombre){
    usuario_t *actual = lista;
    while (actual != NULL) {
        if (strcmp(actual->nombre, nombre) == 0)
            return actual; //encontrado
        actual = actual->sig;
    }
    return NULL; //no existe
}

/*
Inserta un nuevo usuario al inicio de la lista *lista, inicializa todos los campos
Devuelve 0 en éxito, -1 si ya existe un usuario con ese nombre o falla malloc
*/
int insertar_usuario(usuario_t **lista, const char *nombre){
    if (lista == NULL)
        return -1;

    //comprobamos que no exista ya un usuario con ese nombre
    if (buscar_usuario(*lista, nombre) != NULL)
        return -1; //ya existe

    usuario_t *nuevo = (usuario_t *)malloc(sizeof(usuario_t));
    if (nuevo == NULL)
        return -1; //fallo de asignación de memoria

    strncpy(nuevo->nombre, nombre, MAX_USER - 1);
    nuevo->nombre[MAX_USER - 1] = '\0';
    nuevo->conectado = 0;
    nuevo->ip[0] = '\0';
    nuevo->puerto[0] = '\0';
    nuevo->ultimo_id = 0;
    nuevo->pendientes = NULL;
    nuevo->sig = *lista; //insertar al inicio
    *lista = nuevo;

    return 0;
}

/*
Elimina de la lista el usuario con el nombre indicado
Llama a liberar_mensajes para borrar también sus mensajes pendientes
Devuelve 0 en éxito, -1 si el usuario no existe
*/
int eliminar_usuario(usuario_t **lista, const char *nombre){
    if (lista == NULL || *lista == NULL)
        return -1;

    usuario_t *anterior = NULL;
    usuario_t *actual   = *lista;

    while (actual != NULL) {
        if (strcmp(actual->nombre, nombre) == 0) {
            //nodo encontrado, desenlazarlo
            if (anterior == NULL)
                *lista = actual->sig; //era el primero
            else
                anterior->sig = actual->sig;
            liberar_mensajes(actual->pendientes); //liberar mensajes pendientes
            free(actual);
            return 0;
        }
        anterior = actual;
        actual   = actual->sig;
    }

    return -1; //no existe
}


/*
Recorre la lista y libera todos los nodos de usuarios incluyendo sus listas de mensajes pendientes
*/
void liberar_usuarios(usuario_t *lista){
    usuario_t *actual = lista;
    while (actual != NULL) {
        usuario_t *siguiente = actual->sig;
        liberar_mensajes(actual->pendientes); //liberar mensajes pendientes
        free(actual);
        actual = siguiente;
    }
}


/*
Marca al usuario como conectado y guarda su IP y puerto de escucha
*/
void marcar_conectado(usuario_t *u, const char *ip, const char *puerto){
    if (u == NULL)
        return;
    u->conectado = 1;
    strncpy(u->ip, ip, MAX_IP-1); 
    u->ip[MAX_IP-1] = '\0';
    strncpy(u->puerto, puerto, MAX_PORT_STR-1); 
    u->puerto[MAX_PORT_STR-1] = '\0';
}

/*
Marca al usuario como desconectado y limpia los campos ip y puerto
*/
void marcar_desconectado(usuario_t *u){
    if (u == NULL)
        return;
    u->conectado = 0;
    u->ip[0] = '\0';
    u->puerto[0] = '\0';
}
