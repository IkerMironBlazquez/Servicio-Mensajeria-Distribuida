#Compilador y flags
CC = gcc
TIRPC_INC = /usr/include/tirpc
CFLAGS = -g -Wall -Wextra -D_REENTRANT -pthread -I. -I$(TIRPC_INC)
LDFLAGS = -pthread -ltirpc

# Directorios
SRC = src
BUILD = build
RPC_DIR = rpc
RPC_GEN = rpc/generated

#Servidor de mensajería
SERVER_BIN = server

SERVER_SRCS = $(SRC)/server.c \
$(SRC)/protocolo.c \
$(SRC)/servicio_mensajes.c \
$(SRC)/usuarios.c \
$(SRC)/mensajes.c \
$(SRC)/log_rpc_client.c \
$(RPC_GEN)/log_rpc_clnt.c \
$(RPC_GEN)/log_rpc_xdr.c

SERVER_OBJS = $(patsubst %.c,$(BUILD)/%.o,$(notdir $(SERVER_SRCS)))

#Servidor RPC
RPC_BIN = log_rpc_server

RPC_SRCS = $(RPC_DIR)/log_rpc_server.c \
$(RPC_GEN)/log_rpc_svc.c \
$(RPC_GEN)/log_rpc_xdr.c

RPC_OBJS = $(patsubst %.c,$(BUILD)/%.o,$(notdir $(RPC_SRCS)))

#Reglas principales
.PHONY: all rpc rpcgen clean

all: $(SERVER_BIN) $(RPC_BIN)

#Solo el servidor RPC
rpc: $(RPC_BIN)

#Regenerar stubs a partir del fichero .x, usar solo si se modifica log_rpc.x
rpcgen:
	cd $(RPC_DIR) && rpcgen -N -h log_rpc.x > generated/log_rpc.h
	cd $(RPC_DIR) && rpcgen -N -c log_rpc.x > generated/log_rpc_xdr.c
	cd $(RPC_DIR) && rpcgen -N -l log_rpc.x > generated/log_rpc_clnt.c
	cd $(RPC_DIR) && rpcgen -N -m log_rpc.x > generated/log_rpc_svc.c

$(BUILD):
	mkdir -p $(BUILD)

#Enlazar servidor de mensajería
$(SERVER_BIN): $(SERVER_OBJS)
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS)

#Enlazar servidor RPC
$(RPC_BIN): $(RPC_OBJS)
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS)

#Reglas de compilación individuales

#Fuentes en src/, build/<nombre>.o
$(BUILD)/%.o: $(SRC)/%.c | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

#Fuente del servidor RPC
$(BUILD)/log_rpc_server.o: $(RPC_DIR)/log_rpc_server.c | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

#Stubs generados por rpcgen en rpc/generated/
#Se añade -I$(RPC_GEN) para que encuentren "log_rpc.h"
$(BUILD)/log_rpc_clnt.o: $(RPC_GEN)/log_rpc_clnt.c | $(BUILD)
	$(CC) $(CFLAGS) -I$(RPC_GEN) -c $< -o $@

$(BUILD)/log_rpc_svc.o: $(RPC_GEN)/log_rpc_svc.c | $(BUILD)
	$(CC) $(CFLAGS) -I$(RPC_GEN) -Wno-cast-function-type -c $< -o $@

$(BUILD)/log_rpc_xdr.o: $(RPC_GEN)/log_rpc_xdr.c | $(BUILD)
	$(CC) $(CFLAGS) -I$(RPC_GEN) -Wno-unused-variable -c $< -o $@

#Limpieza
clean:
	rm -rf $(BUILD) $(SERVER_BIN) $(RPC_BIN)
