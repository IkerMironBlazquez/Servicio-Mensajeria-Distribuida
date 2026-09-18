#ifndef COMMON_H
#define COMMON_H

//Tamaños máximos
#define MAX_USER 256 //nombre de usuario + '\0'
#define MAX_OP 64 //cadena de operación + '\0'
#define MAX_MESSAGE 256 //mensaje completo incluyendo '\0'
#define MAX_MESSAGE_TXT 255 //caracteres útiles del texto
#define MAX_IP 64 //dirección IP + '\0'
#define MAX_PORT_STR 16 //puerto en cadena + '\0'
#define MAX_FILENAME 256 //nombre de fichero + '\0'
#define MAX_ID_STR 16 //identificador numérico en cadena + '\0'

//Códigos de operacion del servicio
#define SVC_OK 0
#define SVC_USER_EXISTS 1
#define SVC_USER_NOT_FOUND 2
#define SVC_ALREADY_CONNECTED 3
#define SVC_NOT_CONNECTED 4
#define SVC_ERROR 5

//Códigos de respuesta del protocolo
#define PROTO_OK 0
#define PROTO_ERR1 1
#define PROTO_ERR2 2
#define PROTO_ERR3 3

//Constantes booleanas
#ifndef TRUE
#define TRUE 1
#endif
#ifndef FALSE
#define FALSE 0
#endif

//Operaciones del protocolo
#define OP_REGISTER "REGISTER"
#define OP_UNREGISTER "UNREGISTER"
#define OP_CONNECT "CONNECT"
#define OP_DISCONNECT "DISCONNECT"
#define OP_SEND "SEND"
#define OP_SENDATTACH "SENDATTACH"
#define OP_USERS "USERS"

//Operaciones servidor hacia cliente
#define OP_SEND_MSG "SEND MESSAGE"
#define OP_SEND_MSG_ATT "SEND MESSAGE ATTACH"
#define OP_SEND_ACK "SEND MESS ACK"
#define OP_SEND_ACK_ATT "SEND MESS ATTACH ACK"
#define OP_GET_FILE "GET FILE"

#endif
