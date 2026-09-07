from flask import Flask, request, jsonify
import os
import json
import uuid
import urllib.request
import urllib.error
import urllib.parse
import threading
import time

app = Flask(**name**)

# ==========================================

# CONFIGURAÇÃO

# ==========================================

VALOR = "5.00"

TERMINAL_ID = "PAX_Q92__Q92-1734003340"
STORE_ID = "77202273"
POS_ID = "137651952"

INTERVALO_PAGAMENTO = 3

# ==========================================

# CONTROLE DO SISTEMA

# ==========================================

lock = threading.Lock()

ordem_atual = None
pagamento_aprovado = None
cobranca_criada = False

# Guarda as Orders que já foram entregues ao ESP32

ids_processados = set()

# ==========================================

# CRIAR COBRANÇA DE R$ 5,00

# ==========================================

def criar_cobranca():

```
global ordem_atual
global cobranca_criada

token = os.environ.get("MP_ACCESS_TOKEN")

if not token:
    print("ERRO: MP_ACCESS_TOKEN NÃO CONFIGURADO.")
    return None

url = "https://api.mercadopago.com/v1/orders"

referencia = "auto-r5-" + uuid.uuid4().hex[:12]

dados = {
    "type": "point",

    "external_reference": referencia,

    "expiration_time": "PT15M",

    "transactions": {
        "payments": [
            {
                "amount": VALOR
            }
        ]
    },

    "config": {
        "point": {
            "terminal_id": TERMINAL_ID,
            "print_on_terminal": "no_ticket"
        }
    },

    "description": "Venda automatica R$ 5"
}

corpo = json.dumps(dados).encode("utf-8")

requisicao = urllib.request.Request(
    url,
    data=corpo,
    headers={
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json",
        "X-Idempotency-Key": str(uuid.uuid4())
    },
    method="POST"
)

try:

    with urllib.request.urlopen(
        requisicao,
        timeout=20
    ) as resposta:

        resultado = resposta.read().decode("utf-8")

    resultado_json = json.loads(resultado)

    nova_ordem = resultado_json.get("id")

    if not nova_ordem:

        print("ERRO: MERCADO PAGO NÃO RETORNOU ID DA ORDER.")

        print(resultado_json)

        return None

    with lock:

        ordem_atual = nova_ordem
        cobranca_criada = True

    print("")
    print("==========================================")
    print("NOVA COBRANÇA CRIADA")
    print("==========================================")
    print("ORDER:", nova_ordem)
    print("REFERÊNCIA:", referencia)
    print("VALOR: R$ 5,00")
    print("STATUS:", resultado_json.get("status"))
    print("POINT PRONTA PARA PAGAMENTO")
    print("==========================================")
    print("")

    return resultado_json

except urllib.error.HTTPError as erro:

    resposta = erro.read().decode("utf-8")

    print("")
    print("==========================================")
    print("ERRO MERCADO PAGO")
    print("==========================================")
    print("HTTP:", erro.code)
    print(resposta)
    print("==========================================")
    print("")

    return None

except Exception as erro:

    print("")
    print("ERRO AO CRIAR COBRANÇA:")
    print(erro)
    print("")

    return None
```

# ==========================================

# CONSULTAR ORDER NO MERCADO PAGO

# ==========================================

def consultar_ordem(order_id):

```
token = os.environ.get("MP_ACCESS_TOKEN")

if not token:

    print("ERRO: MP_ACCESS_TOKEN NÃO CONFIGURADO.")

    return None

url = (
    "https://api.mercadopago.com/v1/orders/"
    + str(order_id)
)

requisicao = urllib.request.Request(
    url,
    headers={
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json"
    },
    method="GET"
)

try:

    with urllib.request.urlopen(
        requisicao,
        timeout=15
    ) as resposta:

        dados = resposta.read().decode("utf-8")

    resultado = json.loads(dados)

    return resultado

except urllib.error.HTTPError as erro:

    resposta = erro.read().decode("utf-8")

    print("")
    print("ERRO CONSULTANDO ORDER")
    print("HTTP:", erro.code)
    print(resposta)
    print("")

    return None

except Exception as erro:

    print("")
    print("ERRO CONSULTANDO ORDER:")
    print(erro)
    print("")

    return None
```

# ==========================================

# VERIFICAR SE O PAGAMENTO FOI APROVADO

# ==========================================

def verificar_order_aprovada(order_id):

```
dados = consultar_ordem(order_id)

if not dados:

    return False

status = dados.get("status")

status_detail = dados.get("status_detail")

pagamentos = (
    dados
    .get("transactions", {})
    .get("payments", [])
)

print("")
print("==========================================")
print("CONSULTA DE PAGAMENTO")
print("==========================================")
print("ORDER:", order_id)
print("STATUS:", status)
print("STATUS DETAIL:", status_detail)

if pagamentos:

    pagamento = pagamentos[0]

    print(
        "PAYMENT ID:",
        pagamento.get("id")
    )

    print(
        "PAYMENT STATUS:",
        pagamento.get("status")
    )

    print(
        "PAYMENT STATUS DETAIL:",
        pagamento.get("status_detail")
    )

print("==========================================")
print("")

# ======================================
# PAGAMENTO CONFIRMADO
# ======================================

if (
    status == "processed"
    and status_detail == "accredited"
):

    return True

return False
```

# ==========================================

# STATUS DA ORDER PARA DIAGNÓSTICO

# ==========================================

@app.route("/status-order", methods=["GET"])
def status_order():

```
order_id = request.args.get("order_id")

if not order_id:

    return jsonify({
        "erro": "Informe o order_id",
        "exemplo":
            "/status-order?order_id=ORD..."
    }), 400

dados = consultar_ordem(order_id)

if not dados:

    return jsonify({
        "erro":
            "Não foi possível consultar a Order.",
        "order_id": order_id
    }), 500

pagamentos = (
    dados
    .get("transactions", {})
    .get("payments", [])
)

return jsonify({

    "order_id": order_id,

    "status":
        dados.get("status"),

    "status_detail":
        dados.get("status_detail"),

    "payments":
        pagamentos,

    "order_completa":
        dados

}), 200
```

# ==========================================

# WEBHOOK DO MERCADO PAGO

# ==========================================

@app.route("/webhook", methods=["POST"])
def webhook():

```
dados = request.get_json(
    silent=True
) or {}

data_id_url = request.args.get(
    "data.id"
)

tipo_url = request.args.get(
    "type"
)

external_reference_url = (
    request.args.get(
        "data.external_reference"
    )
)

tipo_json = dados.get("type")

action = dados.get("action")

data = dados.get(
    "data",
    {}
)

data_id_json = data.get("id")

data_id = (
    data_id_url
    or data_id_json
)

tipo = (
    tipo_url
    or tipo_json
)

print("")
print("==========================================")
print("WEBHOOK RECEBIDO")
print("==========================================")
print("TIPO:", tipo)
print("ACTION:", action)
print("DATA ID:", data_id)
print(
    "EXTERNAL REFERENCE:",
    external_reference_url
)
print("==========================================")
print("")

# ======================================
# IMPORTANTE:
# NÃO libera o ESP32 apenas porque
# recebeu um webhook.
#
# O webhook apenas informa que houve
# alteração na Order.
#
# A confirmação verdadeira é feita
# consultando a Order na API.
# ======================================

if (
    tipo == "order"
    and data_id
):

    aprovado = verificar_order_aprovada(
        data_id
    )

    if aprovado:

        global pagamento_aprovado

        with lock:

            if data_id not in ids_processados:

                pagamento_aprovado = {
                    "id": data_id,
                    "status": "processado"
                }

                print(
                    "PAGAMENTO APROVADO PELO WEBHOOK."
                )

return jsonify({
    "status": "ok"
}), 200
```

# ==========================================

# /PAGAMENTO

#

# O ESP32 chama esta rota a cada 3 segundos.

#

# Agora o próprio servidor consulta

# diretamente a Order atual.

#

# Não dependemos da thread.

# ==========================================

@app.route("/pagamento", methods=["GET"])
def pagamento():

```
global pagamento_aprovado
global cobranca_criada

# ======================================
# PRIMEIRO:
# Se já existe um pagamento aprovado
# aguardando o ESP32, entrega para ele.
# ======================================

with lock:

    if pagamento_aprovado:

        pagamento_entregue = (
            pagamento_aprovado
        )

        pagamento_aprovado = None

        order_id_entregue = (
            pagamento_entregue["id"]
        )

        ids_processados.add(
            order_id_entregue
        )

        cobranca_criada = False

    else:

        pagamento_entregue = None

# ======================================
# PAGAMENTO JÁ APROVADO
# ======================================

if pagamento_entregue:

    print("")
    print("==========================================")
    print("PAGAMENTO ENTREGUE AO ESP32")
    print("==========================================")
    print(pagamento_entregue)
    print("==========================================")
    print("")

    # ==================================
    # CRIA A PRÓXIMA COBRANÇA
    # ==================================

    time.sleep(1)

    nova_cobranca = criar_cobranca()

    if nova_cobranca:

        print(
            "PRÓXIMA COBRANÇA DE R$ 5,00 PREPARADA."
        )

    else:

        print(
            "ERRO: NÃO FOI POSSÍVEL CRIAR "
            "A PRÓXIMA COBRANÇA."
        )

    return jsonify(
        pagamento_entregue
    ), 200

# ======================================
# NÃO TEM PAGAMENTO GUARDADO
#
# CONSULTA A ORDER ATUAL DIRETAMENTE.
# ======================================

with lock:

    order_id = ordem_atual

if not order_id:

    return jsonify({
        "status": "nenhuma_cobranca"
    }), 200

# ======================================
# SE A ORDER JÁ FOI ENTREGUE,
# NÃO ENTREGA NOVAMENTE.
# ======================================

with lock:

    if order_id in ids_processados:

        return jsonify({
            "status":
                "pagamento_ja_entregue"
        }), 200

# ======================================
# CONSULTA MERCADO PAGO
# ======================================

aprovado = verificar_order_aprovada(
    order_id
)

if not aprovado:

    return jsonify({
        "status":
            "nenhum_pagamento"
    }), 200

# ======================================
# PAGAMENTO APROVADO
# ======================================

with lock:

    if order_id in ids_processados:

        return jsonify({
            "status":
                "pagamento_ja_entregue"
        }), 200

    ids_processados.add(
        order_id
    )

pagamento_entregue = {
    "id": order_id,
    "status": "processado"
}

print("")
print("==========================================")
print("PAGAMENTO APROVADO!")
print("==========================================")
print("ORDER:", order_id)
print("PAGAMENTO DISPONÍVEL PARA O ESP32")
print("==========================================")
print("")

# ======================================
# CRIA A PRÓXIMA COBRANÇA
# ======================================

with lock:

    cobranca_criada = False

time.sleep(1)

nova_cobranca = criar_cobranca()

if nova_cobranca:

    print(
        "PRÓXIMA COBRANÇA DE R$ 5,00 PREPARADA."
    )

else:

    print(
        "ERRO AO PREPARAR A PRÓXIMA COBRANÇA."
    )

return jsonify(
    pagamento_entregue
), 200
```

# ==========================================

# INICIAR

#

# Cria a primeira cobrança de R$ 5,00.

# ==========================================

@app.route("/iniciar", methods=["GET"])
def iniciar():

```
global cobranca_criada
global ordem_atual

with lock:

    if cobranca_criada:

        return jsonify({

            "status":
                "ja_existe_cobranca",

            "ordem":
                ordem_atual,

            "mensagem":
                "A Point Pro 3 já possui "
                "uma cobrança aguardando pagamento."

        }), 200

resultado = criar_cobranca()

if resultado:

    return jsonify({

        "status":
            "cobranca_criada",

        "mensagem":
            "Cobrança automática de R$ 5,00 "
            "criada na Point Pro 3.",

        "mercado_pago":
            resultado

    }), 201

return jsonify({

    "status":
        "erro",

    "mensagem":
        "Não foi possível criar a cobrança."

}), 500
```

# ==========================================

# TERMINAL

#

# Consulta os terminais Mercado Pago.

# ==========================================

@app.route("/terminal", methods=["GET"])
def terminal():

```
token = os.environ.get(
    "MP_ACCESS_TOKEN"
)

if not token:

    return jsonify({
        "erro":
            "MP_ACCESS_TOKEN não configurado"
    }), 500

url = (
    "https://api.mercadopago.com/"
    "terminals/v1/list"
)

parametros = urllib.parse.urlencode({

    "limit": "50",

    "offset": "0",

    "store_id":
        STORE_ID,

    "pos_id":
        POS_ID

})

requisicao = urllib.request.Request(

    url + "?" + parametros,

    headers={

        "Authorization":
            "Bearer " + token,

        "Content-Type":
            "application/json"

    },

    method="GET"
)

try:

    with urllib.request.urlopen(
        requisicao,
        timeout=15
    ) as resposta:

        dados = (
            resposta
            .read()
            .decode("utf-8")
        )

    return jsonify({

        "http_code":
            200,

        "mercado_pago":
            json.loads(dados)

    }), 200

except Exception as erro:

    return jsonify({

        "erro":
            str(erro)

    }), 500
```

# ==========================================

# PÁGINA INICIAL

# ==========================================

@app.route("/", methods=["GET"])
def pagina_inicial():

```
return """
Servidor Mercado Pago + ESP32 funcionando!

Sistema automático R$ 5,00.

/iniciar
/pagamento
/terminal
/status-order?order_id=ORD...
/webhook
"""
```

# ==========================================

# INICIALIZAÇÃO

# ==========================================

if **name** == "**main**":

```
app.run(
    host="0.0.0.0",
    port=10000
)

### O que mudou

A principal mudança é esta:

**Antes:** o servidor dependia de uma thread em segundo plano para perceber o pagamento.

**Agora:** o ESP32 já consulta `/pagamento` a cada 3 segundos, então o próprio `/pagamento` consulta diretamente a Order no Mercado Pago e só responde `processado` quando encontrar:

* `status = processed`
* `status_detail = accredited`

Isso elimina uma parte importante do problema que estávamos investigando.

### Faça exatamente assim

1. Abra o GitHub do projeto.
2. Abra `server.py`.
3. Clique no **lápis (Editar)**.
4. Aperte **Ctrl+A**.
5. Apague tudo.
6. Cole **todo o código acima**.
7. Clique em **Confirmar alterações**.
8. Aguarde o Render mostrar **Deploy succeeded / Live**.

**Não faça nenhum pagamento ainda.**

Depois que aparecer **Live**, abra:

e confirme que agora aparecem também `/pagamento`, `/terminal` e `/status-order`.

Aí fazemos o próximo teste de forma controlada.
