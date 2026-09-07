from flask import Flask, request, jsonify
import threading
import os
import json
import uuid
import urllib.request
import urllib.error
import urllib.parse
import time

app = Flask(__name__)

# ==========================================================
# CONFIGURAÇÃO
# ==========================================================

VALOR = "5.00"

TERMINAL_ID = "PAX_Q92__Q92-1734003340"

INTERVALO_VERIFICACAO = 3


# ==========================================================
# CONTROLE
# ==========================================================

lock = threading.Lock()

pagamento_aprovado = None

ordem_atual = None

cobranca_criada = False

ids_processados = set()


# ==========================================================
# CRIAR COBRANÇA DE R$ 5,00
# ==========================================================

def criar_cobranca():

    global ordem_atual
    global cobranca_criada

    token = os.environ.get("MP_ACCESS_TOKEN")

    if not token:

        print("ERRO: MP_ACCESS_TOKEN não configurado.")

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

        ordem_atual = resultado_json.get("id")

        cobranca_criada = True

        print("")
        print("==========================================")
        print("NOVA COBRANÇA CRIADA")
        print("==========================================")
        print("ORDEM:", ordem_atual)
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


# ==========================================================
# CONSULTAR ORDER DIRETAMENTE NO MERCADO PAGO
# ==========================================================

def consultar_ordem(order_id):

    token = os.environ.get("MP_ACCESS_TOKEN")

    if not token:

        print("ERRO: MP_ACCESS_TOKEN não configurado.")

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

        print("ERRO CONSULTANDO ORDER:")
        print("HTTP:", erro.code)
        print(resposta)

        return None

    except Exception as erro:

        print("ERRO CONSULTANDO ORDER:")
        print(erro)

        return None


# ==========================================================
# VERIFICAR SE PAGAMENTO FOI APROVADO
# ==========================================================

def verificar_pagamento():

    global pagamento_aprovado
    global cobranca_criada

    while True:

        time.sleep(INTERVALO_VERIFICACAO)

        with lock:

            order_id = ordem_atual
            ja_tem_pagamento = pagamento_aprovado is not None

        if not order_id:
            continue

        if ja_tem_pagamento:
            continue

        dados = consultar_ordem(order_id)

        if not dados:
            continue

        status = dados.get("status")

        status_detail = dados.get("status_detail")

        print(
            "CONSULTA ORDER:",
            order_id,
            "| STATUS:",
            status,
            "| DETALHE:",
            status_detail
        )

        if status == "processed":

            with lock:

                if order_id in ids_processados:

                    continue

                ids_processados.add(order_id)

                pagamento_aprovado = {

                    "id": str(order_id),

                    "status": "processado"

                }

                cobranca_criada = False

            print("")
            print("==========================================")
            print("PAGAMENTO APROVADO!")
            print("==========================================")
            print("ORDER:", order_id)
            print("STATUS:", status)
            print("STATUS DETAIL:", status_detail)
            print("PAGAMENTO DISPONÍVEL PARA O ESP32")
            print("==========================================")
            print("")


# ==========================================================
# WEBHOOK
# ==========================================================

@app.route("/webhook", methods=["POST"])
def webhook():

    dados = request.get_json(silent=True) or {}

    data_id_url = request.args.get("data.id")

    tipo_url = request.args.get("type")

    external_reference_url = request.args.get(
        "data.external_reference"
    )

    tipo_json = dados.get("type")

    action = dados.get("action")

    data = dados.get("data", {})

    data_id_json = data.get("id")

    data_id = data_id_url or data_id_json

    tipo = tipo_url or tipo_json

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
    print("CORPO COMPLETO:")
    print(json.dumps(
        dados,
        indent=2,
        ensure_ascii=False
    ))
    print("==========================================")
    print("")

    return jsonify({
        "status": "ok"
    }), 200


# ==========================================================
# ESP32 CONSULTA PAGAMENTO
# ==========================================================

@app.route("/pagamento", methods=["GET"])
def pagamento():

    global pagamento_aprovado
    global cobranca_criada

    pagamento_entregue = None

    with lock:

        if pagamento_aprovado:

            pagamento_entregue = pagamento_aprovado

            pagamento_aprovado = None

    if pagamento_entregue:

        print("")
        print("==========================================")
        print("PAGAMENTO ENTREGUE AO ESP32")
        print(pagamento_entregue)
        print("==========================================")
        print("")

        time.sleep(1)

        with lock:

            existe_cobranca = cobranca_criada

        if not existe_cobranca:

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

        return jsonify(pagamento_entregue), 200

    return jsonify({
        "status": "nenhum_pagamento"
    }), 200


# ==========================================================
# INICIAR PRIMEIRA COBRANÇA
# ==========================================================

@app.route("/iniciar", methods=["GET"])
def iniciar():

    global cobranca_criada
    global ordem_atual

    with lock:

        if cobranca_criada:

            return jsonify({

                "status": "ja_existe_cobranca",

                "ordem": ordem_atual,

                "mensagem":
                    "A Point Pro 3 já possui uma "
                    "cobrança aguardando pagamento."

            }), 200

    resultado = criar_cobranca()

    if resultado:

        return jsonify({

            "status": "cobranca_criada",

            "mensagem":
                "Cobrança automática de R$ 5,00 "
                "criada na Point Pro 3.",

            "mercado_pago": resultado

        }), 201

    return jsonify({

        "status": "erro",

        "mensagem":
            "Não foi possível criar a cobrança."

    }), 500


# ==========================================================
# CONSULTAR TERMINAL
# ==========================================================

@app.route("/terminal", methods=["GET"])
def terminal():

    token = os.environ.get("MP_ACCESS_TOKEN")

    if not token:

        return jsonify({
            "erro": "MP_ACCESS_TOKEN não configurado"
        }), 500

    url = "https://api.mercadopago.com/terminals/v1/list"

    parametros = urllib.parse.urlencode({

        "limit": "50",

        "offset": "0",

        "store_id": "77202273",

        "pos_id": "137651952"

    })

    requisicao = urllib.request.Request(

        url + "?" + parametros,

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

        return jsonify({

            "http_code": 200,

            "mercado_pago": json.loads(dados)

        }), 200

    except Exception as erro:

        return jsonify({

            "erro": str(erro)

        }), 500


# ==========================================================
# PÁGINA INICIAL
# ==========================================================

@app.route("/", methods=["GET"])
def pagina_inicial():

    return """
    Servidor Mercado Pago + ESP32 funcionando!

    Sistema automático R$ 5,00.

    Use /iniciar para preparar a primeira cobrança.
    """


# ==========================================================
# INICIAR SERVIDOR
# ==========================================================

if __name__ == "__main__":

    thread = threading.Thread(
        target=verificar_pagamento,
        daemon=True
    )

    thread.start()

    app.run(
        host="0.0.0.0",
        port=10000
    )
