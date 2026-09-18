#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <rpc/pmap_clnt.h>
#include "rpc/generated/log_rpc.h"

//Declaracion de la funcion de despacho generada por rpcgen en log_rpc_svc.c
extern void log_prog_1(struct svc_req *rqstp, SVCXPRT *transp);

/*
Implementación del procedimiento remoto LOG_OPERATION
Imprime por pantalla la operación realizada por el usuario
*/
int *
log_operation_1_svc(log_request req, struct svc_req *rqstp)
{
    static int result;

    (void)rqstp; //parametro obligatorio de la firma RPC, no se usa

    //Si hay nombre de fichero se imprime junto a la operacion (caso SENDATTACH)
    if (req.filename != NULL && req.filename[0] != '\0') {
        printf("%s\t%s\t%s\n", req.username, req.operation, req.filename);
    } else {
        printf("%s\t%s\n", req.username, req.operation);
    }
    fflush(stdout);

    result = 0;
    return &result;
}

/*
Libera los recursos del resultado de una llamada RPC
Requerido por el framework ONC-RPC generado por rpcgen
*/
int
log_prog_1_freeresult(SVCXPRT *transp, xdrproc_t xdr_result, caddr_t result)
{
    (void)transp;
    xdr_free(xdr_result, result);
    return 1;
}

/*
Punto de entrada del servidor RPC
Desregistra el programa en el portmapper, crea transporte TCP,
registra el servicio y entra en el bucle de atención de peticiones
*/
int
main(int argc, char *argv[])
{
    SVCXPRT *transp;

    (void)argc; (void)argv;

    //Limpiar posibles registros previos en el portmapper
    pmap_unset(LOG_PROG, LOG_VERS);

    //Crear transporte TCP
    transp = svctcp_create(RPC_ANYSOCK, 0, 0);
    if (transp == NULL) {
        fprintf(stderr, "log_rpc_server: no se puede crear el servicio TCP\n");
        exit(1);
    }

    //Registrar el programa con el portmapper usando TCP
    if (!svc_register(transp, LOG_PROG, LOG_VERS, log_prog_1, IPPROTO_TCP)) {
        fprintf(stderr, "log_rpc_server: no se puede registrar el servicio\n");
        exit(1);
    }

    printf("log_rpc_server: escuchando peticiones (TCP)...\n");
    fflush(stdout);

    //Entrar en el bucle de atencion de peticiones RPC
    svc_run();

    //svc_run no debería retornar
    fprintf(stderr, "log_rpc_server: svc_run finalizó inesperadamente\n");
    exit(1);
}

