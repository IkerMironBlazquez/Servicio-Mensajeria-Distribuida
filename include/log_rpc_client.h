#ifndef LOG_RPC_CLIENT_H
#define LOG_RPC_CLIENT_H

/*
Inicializa la conexión con el servidor RPC
Lee la variable de entorno LOG_RPC_IP para obtener la IP del servidor
Devuelve 0 en éxito, -1 si no se pudo conectar o la variable no está definida
 */
int log_rpc_init(void);

/*
Registra una operación en el servidor RPC
username es el nombre del usuario que realiza la operación
operation es el nombre de la operación (REGISTER, CONNECT, SEND, etc.)
filename es el nombre del fichero adjunto, solo utilizado para SENDATTACH, NULL en otro caso
Devuelve 0 en éxito, -1 en error
 */
int log_rpc_log(const char *username, const char *operation, const char *filename);

/*
Libera los recursos del cliente RPC
 */
void log_rpc_destroy(void);

#endif
