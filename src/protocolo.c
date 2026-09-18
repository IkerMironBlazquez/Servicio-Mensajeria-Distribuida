#include <sys/socket.h>
#include <string.h>
#include <errno.h>
#include "include/protocolo.h"
#include "include/common.h"

/*
Envía exactamente len bytes desde buf hacia sock, bucle hasta enviar todos los bytes
Devuelve 0 en éxito, -1 en error 
*/
int send_all(int sock, const void *buf, size_t len){
    size_t enviados = 0; //bytes ya enviados
    const char *p = (const char *)buf; //puntero de trabajo sobre el buffer

    while (enviados < len) {
        ssize_t n = send(sock, p + enviados, len - enviados, 0);
        if (n <= 0)
            return -1; //error o conexión cerrada
        enviados += (size_t)n;
    }
    return 0;
}


/*
Recibe exactamente len bytes en buf desde sock, bucle hasta recibir todos los bytes
Devuelve 0 en éxito, -1 si hay error
*/
int recv_all(int sock, void *buf, size_t len){
    size_t recibidos = 0; //bytes ya recibidos
    char *p = (char *)buf; //puntero de trabajo sobre el buffer

    while (recibidos < len) {
        ssize_t n = recv(sock, p + recibidos, len - recibidos, 0);
        if (n <= 0)
            return -1; //error o conexión cerrada
        recibidos += (size_t)n;
    }
    return 0;
}


/*
Envía la cadena str terminada en '\0', incluyendo el propio '\0'
Devuelve 0 en éxito, -1 en error
*/
int send_string(int sock, const char *str){
    size_t len = strlen(str) + 1; //+1 para incluir el '\0'
    return send_all(sock, str, len);
}


/*
Recibe una cadena terminada en '\0' y la almacena en buf
Lee byte a byte hasta encontrar '\0', sin superar max_len bytes (incluye el '\0')
Si se supera el tamaño máximo sin encontrar '\0', devuelve -1
*/
int recv_string(int sock, char *buf, size_t max_len){
    size_t pos = 0;
    unsigned char c;

    while (pos < max_len) {
        if (recv_all(sock, &c, 1) < 0)
            return -1; //error de red
        buf[pos++] = (char)c;
        if (c == '\0')
            return 0; //cadena recibida correctamente
    }
    //Se superó max_len sin encontrar '\0', error de protocolo
    return -1;
}


/*
Envía un byte de código de respuesta
Devuelve 0 en éxito, -1 en error
*/
int send_code(int sock, unsigned char code){
    return send_all(sock, &code, 1);
}


/*
Recibe un byte de código de respuesta y lo guarda en *code
Devuelve 0 en éxito, -1 en error
*/
int recv_code(int sock, unsigned char *code){
    return recv_all(sock, code, 1);
}
