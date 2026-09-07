from flask import Flask, request, jsonify
import os
import json
import uuid
import urllib.request
import urllib.error
import urllib.parse
import time
import threading

app = Flask(__name__)

VALOR = "5.00"
TERMINAL_ID = "PAX_Q92__Q92-1734003340"
STORE_ID = "77202273"
POS_ID = "137651952"

lock = threading.Lock()

ordem_atual = None
pagamento_aprovado = None
cobranca_criada = False
ids_processados = set()


def criar_cobranca():
    global ordem_atual
    global cobranca_criada

    token = os.environ.get("MP_ACCESS_TOKEN")

    if not token:
        print("ERRO: MP_ACCESS_TOKEN NÃO CONFIGURADO")
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
        with urllib.request.urlopen(requisicao, timeout=20) as resposta:
            resultado = resposta.read().decode("utf-8")

        resultado_json = json.loads(resultado)
        nova_ordem = resultado_json.get("id")

        if not nova_ordem:
            print("ERRO: ORDER NÃO RETORNOU ID")
            print(resultado_json)
            return None

        with lock:
            ordem_atual = nova_ordem
            cobranca_criada = True

        print("NOVA COBRANÇA CRIADA")
        print("ORDER:", nova_ordem)
        print("VALOR: R$ 5,00")

        return resultado_json

    except urllib.error.HTTPError as erro:
        resposta = erro.read().decode("utf-8")
        print("ERRO MERCADO PAGO")
        print("HTTP:", erro.code)
        print(resposta)
        return None

    except Exception as erro:
        print("ERRO AO CRIAR COBRANÇA:", erro)
        return None


def consultar_ordem(order_id):
    token = os.environ.get("MP_ACCESS_TOKEN")

    if not token:
        print("ERRO: MP_ACCESS_TOKEN NÃO CONFIGURADO")
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
        with urllib.request.urlopen(requisicao, timeout=15) as resposta:
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


def verificar_order_aprovada(order_id):
    dados = consultar_ordem(order_id)

    if not dados:
        return False

    status = dados.get("status")
    status_detail = dados.get("status_detail")

    print("ORDER:", order_id)
    print("STATUS:", status)
    print("STATUS DETAIL:", status_detail)

    if status == "processed" and status_detail == "accredited":
        return True

    return False


@app.route("/status-order", methods=["GET"])
def status_order():
    order_id = request.args.get("order_id")

    if not order_id:
        return jsonify({
            "erro": "Informe o order_id"
        }), 400

    dados = consultar_ordem(order_id)

    if not dados:
        return jsonify({
            "erro": "Não foi possível consultar a Order.",
            "order_id": order_id
        }), 500

    pagamentos = (
        dados
        .get("transactions", {})
        .get("payments", [])
    )

    return jsonify({
        "order_id": order_id,
        "status": dados.get("status"),
        "status_detail": dados.get("status_detail"),
        "payments": pagamentos
    }), 200


@app.route("/webhook", methods=["POST"])
def webhook():
    global pagamento_aprovado

    dados = request.get_json(silent=True) or {}

    data_id_url = request.args.get("data.id")
    tipo_url = request.args.get("type")

    tipo_json = dados.get("type")
    action = dados.get("action")

    data = dados.get("data", {})
    data_id_json = data.get("id")

    data_id = data_id_url or data_id_json
    tipo = tipo_url or tipo_json

    print("WEBHOOK RECEBIDO")
    print("TIPO:", tipo)
    print("ACTION:", action)
    print("DATA ID:", data_id)

    if tipo == "order" and data_id:
        aprovado = verificar_order_aprovada(data_id)

        if aprovado:
            with lock:
                if data_id not in ids_processados:
                    pagamento_aprovado = {
                        "id": data_id,
                        "status": "processado"
                    }

    return jsonify({
        "status": "ok"
    }), 200


@app.route("/pagamento", methods=["GET"])
def pagamento():
    global pagamento_aprovado
    global cobranca_criada

    with lock:
        if pagamento_aprovado:
            pagamento_entregue = pagamento_aprovado
            pagamento_aprovado = None

            order_id_entregue = pagamento_entregue["id"]
            ids_processados.add(order_id_entregue)
            cobranca_criada = False
        else:
            pagamento_entregue = None

    if pagamento_entregue:
        print("PAGAMENTO ENTREGUE AO ESP32")
        print(pagamento_entregue)

        time.sleep(1)

        nova_cobranca = criar_cobranca()

        if nova_cobranca:
            print("PRÓXIMA COBRANÇA PREPARADA")

        return jsonify(pagamento_entregue), 200

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

    aprovado = verificar_order_aprovada(order_id)

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

    pagamento_entregue = {
        "id": order_id,
        "status": "processado"
    }

    print("PAGAMENTO APROVADO")
    print("ORDER:", order_id)

    with lock:
        cobranca_criada = False

    time.sleep(1)

    nova_cobranca = criar_cobranca()

    if nova_cobranca:
        print("PRÓXIMA COBRANÇA DE R$ 5,00 PREPARADA")
    else:
        print("ERRO AO PREPARAR PRÓXIMA COBRANÇA")

    return jsonify(pagamento_entregue), 200


@app.route("/iniciar", methods=["GET"])
def iniciar():
    global cobranca_criada

    with lock:
        if cobranca_criada:
            return jsonify({
                "status": "ja_existe_cobranca",
                "ordem": ordem_atual
            }), 200

    resultado = criar_cobranca()

    if resultado:
        return jsonify({
            "status": "cobranca_criada",
            "mensagem": "Cobrança de R$ 5,00 criada na Point Pro 3",
            "mercado_pago": resultado
        }), 201

    return jsonify({
        "status": "erro",
        "mensagem": "Não foi possível criar a cobrança"
    }), 500


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
        "store_id": STORE_ID,
        "pos_id": POS_ID
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
        with urllib.request.urlopen(requisicao, timeout=15) as resposta:
            dados = resposta.read().decode("utf-8")

        return jsonify({
            "http_code": 200,
            "mercado_pago": json.loads(dados)
        }), 200

    except Exception as erro:
        return jsonify({
            "erro": str(erro)
        }), 500


@app.route("/", methods=["GET"])
def pagina_inicial():
    return "Servidor Mercado Pago + ESP32 funcionando!"


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=10000
    )
