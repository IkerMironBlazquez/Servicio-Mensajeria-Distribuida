#ifndef PROTOCOLO_H
#define PROTOCOLO_H

#include <stddef.h>

/*
Envía exactamente len bytes desde buf hacia sock
Devuelve 0 en éxito, -1 en error
*/
int send_all(int sock, const void *buf, size_t len);

/*
Recibe exactamente len bytes en buf desde sock
Devuelve 0 en éxito, -1 en error
*/
int recv_all(int sock, void *buf, size_t len);

/*
Envía la cadena str terminada en '\0', incluyendo el '\0'
Devuelve 0 en éxito, -1 en error
*/
int send_string(int sock, const char *str);

/*
Recibe una cadena terminada en '\0' y la almacena en buf con máx max_len bytes
Devuelve 0 en éxito, -1 en error
*/
int recv_string(int sock, char *buf, size_t max_len);

/*
Envía un byte de código de respuesta
Devuelve 0 en éxito, -1 en error
*/
int send_code(int sock, unsigned char code);

/*
Recibe un byte de código de respuesta en *code
Devuelve 0 en éxito, -1 en error
*/
int recv_code(int sock, unsigned char *code);

#endif