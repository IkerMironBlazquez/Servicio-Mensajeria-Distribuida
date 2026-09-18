#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include "include/log_rpc_client.h"
#include "include/common.h"
#include "rpc/generated/log_rpc.h"

//IP del servidor RPC, leída de la variable de entorno LOG_RPC_IP en log_rpc_init
static char rpc_server_ip[MAX_IP] = {0};

//1 si LOG_RPC_IP estaba definida al iniciar 0 si el RPC está desactivado
static int rpc_enabled = 0;

/*
Lee la variable de entorno LOG_RPC_IP y guarda la IP del servidor RPC
Si la variable no está definida, el cliente RPC queda desactivado
Devuelve 0 si la variable estaba definida, -1 en caso contrario
*/
int log_rpc_init(void){
    const char *ip = getenv("LOG_RPC_IP");
    if (ip == NULL) {
        rpc_enabled = 0;
        return -1;
    }

    strncpy(rpc_server_ip, ip, MAX_IP - 1);
    rpc_server_ip[MAX_IP - 1] = '\0';
    rpc_enabled = 1;
    return 0;
}

/*
Registra una operación en el servidor RPC
username es el nombre del usuario que realiza la operación
operation es el nombre de la operación
filename es el nombre del fichero adjunto
*/
int log_rpc_log(const char *username, const char *operation, const char *filename){
    CLIENT *clnt;
    log_request req;
    int *result;

    //Si la variable de entorno no estaba definida, no hacer nada
    if (!rpc_enabled)
        return 0;

    //Crear cliente RPC TCP; si falla, no interrumpir el servicio de mensajería
    clnt = clnt_create(rpc_server_ip, LOG_PROG, LOG_VERS, "tcp");
    if (clnt == NULL)
        return 0;

    //Rellenar la petición filename vacío si no se usa
    req.username  = (char *)username;
    req.operation = (char *)operation;
    req.filename  = (filename != NULL && filename[0] != '\0') ? (char *)filename : "";

    //LLamar al procedimiento remoto
    result = log_operation_1(req, clnt);

    //Comprobar el resultado antes de liberar el cliente
    if (result == NULL) {
        clnt_perror(clnt, "Error en la llamada RPC log_operation");
        clnt_destroy(clnt);
        return -1;
    }

    clnt_destroy(clnt);
    return *result;
}

/*
Desactiva el cliente RPC
Tras esta llamada log_rpc_log actúa como no-op
*/
void log_rpc_destroy(void){
    rpc_enabled = 0;
    rpc_server_ip[0] = '\0';
}

