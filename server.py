from flask import Flask, request, jsonify
import os
import json
import uuid
import urllib.request
import urllib.error
import urllib.parse
import threading

app = Flask(__name__)

VALOR = "5.00"

TERMINAL_ID = "PAX_Q92__Q92-1734003340"
STORE_ID = "77202273"
POS_ID = "137651952"

lock = threading.Lock()

ordem_atual = None
cobranca_criada = False

ids_processados = set()


def consultar_ordem(order_id):

    token = os.environ.get("MP_ACCESS_TOKEN")

    if not token:
        print("ERRO: MP_ACCESS_TOKEN NAO CONFIGURADO")
        return None

    url = "https://api.mercadopago.com/v1/orders/" + str(order_id)

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

        return json.loads(dados)

    except urllib.error.HTTPError as erro:

        resposta = erro.read().decode("utf-8")

        print("ERRO CONSULTANDO ORDER")
        print("HTTP:", erro.code)
        print(resposta)

        return None

    except Exception as erro:

        print("ERRO CONSULTANDO ORDER:", erro)

        return None


def pagamento_realmente_aprovado(order_id):

    dados = consultar_ordem(order_id)

    if not dados:
        return False

    status_order = dados.get("status")
    status_detail_order = dados.get("status_detail")

    print("================================")
    print("VERIFICANDO ORDER")
    print("ORDER:", order_id)
    print("STATUS:", status_order)
    print("STATUS DETAIL:", status_detail_order)

    pagamentos = (
        dados
        .get("transactions", {})
        .get("payments", [])
    )

    if not pagamentos:

        print("NENHUM PAGAMENTO ENCONTRADO")

        return False

    pagamento_valido = False

    for pagamento in pagamentos:

        payment_id = pagamento.get("id")
        amount = str(pagamento.get("amount", ""))
        status = pagamento.get("status")
        status_detail = pagamento.get("status_detail")

        print("PAYMENT:", payment_id)
        print("VALOR:", amount)
        print("STATUS PAYMENT:", status)
        print("STATUS DETAIL PAYMENT:", status_detail)

        if (
            amount == VALOR
            and status == "processed"
            and status_detail == "accredited"
        ):

            pagamento_valido = True

    if status_order != "processed":

        print("ORDER AINDA NAO ESTA PROCESSED")

        return False

    if status_detail_order != "accredited":

        print("ORDER NAO ESTA ACCREDITED")

        return False

    if not pagamento_valido:

        print("PAGAMENTO NAO FOI CONFIRMADO")

        return False

    print("================================")
    print("PAGAMENTO REAL CONFIRMADO")
    print("ORDER:", order_id)
    print("VALOR CONFIRMADO: R$ 5,00")
    print("================================")

    return True


def criar_cobranca():

    global ordem_atual
    global cobranca_criada

    token = os.environ.get("MP_ACCESS_TOKEN")

    if not token:

        print("ERRO: MP_ACCESS_TOKEN NAO CONFIGURADO")

        return None

    with lock:

        if cobranca_criada and ordem_atual:

            print("JA EXISTE UMA COBRANCA ATIVA")

            return None

    url = "https://api.mercadopago.com/v1/orders"

    referencia = (
        "auto-r5-" +
        uuid.uuid4().hex[:12]
    )

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

            "Authorization":
                "Bearer " + token,

            "Content-Type":
                "application/json",

            "X-Idempotency-Key":
                str(uuid.uuid4())

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

            print("ERRO: ORDER NAO RETORNOU ID")

            print(resultado_json)

            return None

        with lock:

            ordem_atual = nova_ordem
            cobranca_criada = True

        print("================================")
        print("NOVA COBRANCA CRIADA")
        print("ORDER:", nova_ordem)
        print("VALOR: R$ 5,00")
        print("================================")

        return resultado_json

    except urllib.error.HTTPError as erro:

        resposta = erro.read().decode("utf-8")

        print("ERRO MERCADO PAGO")
        print("HTTP:", erro.code)
        print(resposta)

        return None

    except Exception as erro:

        print("ERRO AO CRIAR COBRANCA:", erro)

        return None


@app.route("/pagamento", methods=["GET"])
def pagamento():

    with lock:

        order_id = ordem_atual

    if not order_id:

        return jsonify({
            "status": "nenhuma_cobranca"
        }), 200

    with lock:

        if order_id in ids_processados:

            return jsonify({
                "status": "pagamento_ja_entregue"
            }), 200

    aprovado = pagamento_realmente_aprovado(
        order_id
    )

    if not aprovado:

        return jsonify({
            "status": "nenhum_pagamento"
        }), 200

    with lock:

        if order_id in ids_processados:

            return jsonify({
                "status": "pagamento_ja_entregue"
            }), 200

        ids_processados.add(order_id)

    print("================================")
    print("PAGAMENTO LIBERADO PARA O ESP32")
    print("ORDER:", order_id)
    print("================================")

    return jsonify({

        "id": order_id,

        "status": "processado"

    }), 200


@app.route("/webhook", methods=["POST"])
def webhook():

    dados = request.get_json(
        silent=True
    ) or {}

    data_id_url = request.args.get(
        "data.id"
    )

    tipo_url = request.args.get(
        "type"
    )

    tipo_json = dados.get(
        "type"
    )

    action = dados.get(
        "action"
    )

    data = dados.get(
        "data",
        {}
    )

    data_id_json = data.get(
        "id"
    )

    data_id = (
        data_id_url
        or data_id_json
    )

    tipo = (
        tipo_url
        or tipo_json
    )

    print("================================")
    print("WEBHOOK RECEBIDO")
    print("TIPO:", tipo)
    print("ACTION:", action)
    print("DATA ID:", data_id)
    print("================================")

    if tipo != "order":

        return jsonify({
            "status": "ok"
        }), 200

    if not data_id:

        return jsonify({
            "status": "ok"
        }), 200

    if action != "order.processed":

        print(
            "WEBHOOK NAO E DE ORDER.PROCESSED"
        )

        return jsonify({
            "status": "ok"
        }), 200

    with lock:

        if data_id in ids_processados:

            print(
                "ORDER JA FOI PROCESSADA"
            )

            return jsonify({
                "status": "ok"
            }), 200

    aprovado = pagamento_realmente_aprovado(
        data_id
    )

    if not aprovado:

        print(
            "WEBHOOK RECEBIDO, MAS PAGAMENTO NAO CONFIRMADO"
        )

        return jsonify({
            "status": "ok"
        }), 200

    print(
        "WEBHOOK CONFIRMOU PAGAMENTO REAL"
    )

    return jsonify({
        "status": "ok"
    }), 200


@app.route("/iniciar", methods=["GET"])
def iniciar():

    with lock:

        if cobranca_criada and ordem_atual:

            return jsonify({

                "status":
                    "ja_existe_cobranca",

                "ordem":
                    ordem_atual

            }), 200

    resultado = criar_cobranca()

    if resultado:

        return jsonify({

            "status":
                "cobranca_criada",

            "mensagem":
                "Cobranca de R$ 5,00 criada na Point Pro 3",

            "mercado_pago":
                resultado

        }), 201

    return jsonify({

        "status":
            "erro",

        "mensagem":
            "Nao foi possivel criar a cobranca"

    }), 500


@app.route("/proxima", methods=["GET"])
def proxima():

    global ordem_atual
    global cobranca_criada

    with lock:

        order_id = ordem_atual

        if not order_id:

            cobranca_criada = False

        else:

            if order_id not in ids_processados:

                return jsonify({

                    "status":
                        "aguardando_pagamento",

                    "ordem":
                        order_id

                }), 200

    resultado = criar_cobranca()

    if resultado:

        return jsonify({

            "status":
                "proxima_cobranca_criada",

            "mercado_pago":
                resultado

        }), 201

    return jsonify({

        "status":
            "erro",

        "mensagem":
            "Nao foi possivel criar a proxima cobranca"

    }), 500


@app.route("/status-order", methods=["GET"])
def status_order():

    order_id = request.args.get(
        "order_id"
    )

    if not order_id:

        return jsonify({

            "erro":
                "Informe o order_id"

        }), 400

    dados = consultar_ordem(
        order_id
    )

    if not dados:

        return jsonify({

            "erro":
                "Nao foi possivel consultar a Order.",

            "order_id":
                order_id

        }), 500

    pagamentos = (
        dados
        .get("transactions", {})
        .get("payments", [])
    )

    return jsonify({

        "order_id":
            order_id,

        "status":
            dados.get("status"),

        "status_detail":
            dados.get("status_detail"),

        "payments":
            pagamentos

    }), 200


@app.route("/terminal", methods=["GET"])
def terminal():

    token = os.environ.get(
        "MP_ACCESS_TOKEN"
    )

    if not token:

        return jsonify({

            "erro":
                "MP_ACCESS_TOKEN nao configurado"

        }), 500

    url = (
        "https://api.mercadopago.com/"
        "terminals/v1/list"
    )

    parametros = urllib.parse.urlencode({

        "limit":
            "50",

        "offset":
            "0",

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

            dados = resposta.read().decode(
                "utf-8"
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


@app.route("/", methods=["GET"])
def pagina_inicial():

    return (
        "Servidor Mercado Pago + ESP32 funcionando!"
    )


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=10000
    )
