/*
 * log_rpc.x  --  Interfaz ONC-RPC para el servicio de registro de operaciones.
 *
 * El servidor de mensajería (cliente RPC) envía al servidor RPC:
 *   - el nombre del usuario
 *   - la operación realizada
 *   - el nombre del fichero adjunto (solo para SENDATTACH; cadena vacía en otro caso)
 *
 * Generar los stubs con:
 *   rpcgen -N -a log_rpc.x
 * o bien de forma selectiva:
 *   rpcgen -N -h log_rpc.x  >  generated/log_rpc.h
 *   rpcgen -N -c log_rpc.x  >  generated/log_rpc_xdr.c
 *   rpcgen -N -l log_rpc.x  >  generated/log_rpc_clnt.c
 *   rpcgen -N -m log_rpc.x  >  generated/log_rpc_svc.c
 */

/* Estructura que encapsula los parámetros de una operación */
struct log_request {
    string username<256>;    /* nombre del usuario */
    string operation<64>;    /* nombre de la operación */
    string filename<256>;    /* nombre del fichero (vacío si no aplica) */
};

/* Programa RPC */
program LOG_PROG {
    version LOG_VERS {
        /* Registra una operación; devuelve 0 en éxito */
        int LOG_OPERATION(log_request) = 1;
    } = 1;
} = 0x20000001;
