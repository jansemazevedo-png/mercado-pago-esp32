python
from flask import Flask, request, jsonify
import os
import json
import uuid
import urllib.request
import urllib.error
import threading
import time

app = Flask(__name__)

VALOR = "5.00"

TERMINAL_ID = "PAX_Q92__Q92-1734118066"
STORE_ID = "77202273"
POS_ID = "137651952"

API_ORDERS = "https://api.mercadopago.com/v1/orders"

INTERVALO_VERIFICACAO = 3
ESPERA_PROXIMA_COBRANCA = 3

lock = threading.Lock()

ordem_atual = None
cobranca_criada = False
criando_cobranca = False

ultimo_webhook = None


def consultar_ordem(order_id):
    token = os.environ.get("MP_ACCESS_TOKEN")

    if not token:
        print("ERRO: MP_ACCESS_TOKEN NAO CONFIGURADO", flush=True)
        return None

    url = API_ORDERS + "/" + str(order_id)

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

        print("CONSULTA ORDER OK:", order_id, flush=True)

        return json.loads(dados)

    except urllib.error.HTTPError as erro:
        resposta = erro.read().decode("utf-8")

        print("========================================", flush=True)
        print("ERRO CONSULTANDO ORDER", flush=True)
        print("ORDER:", order_id, flush=True)
        print("HTTP:", erro.code, flush=True)
        print("RESPOSTA MERCADO PAGO:", resposta, flush=True)
        print("========================================", flush=True)

        return None

    except Exception as erro:
        print("========================================", flush=True)
        print("ERRO CONSULTANDO ORDER:", str(erro), flush=True)
        print("========================================", flush=True)

        return None


def criar_cobranca():
    global ordem_atual
    global cobranca_criada
    global criando_cobranca

    token = os.environ.get("MP_ACCESS_TOKEN")

    if not token:
        print("ERRO: MP_ACCESS_TOKEN NAO CONFIGURADO", flush=True)
        return None

    with lock:
        if criando_cobranca:
            print("JA EXISTE UMA COBRANCA SENDO CRIADA", flush=True)
            return None

        if cobranca_criada and ordem_atual:
            print("JA EXISTE UMA COBRANCA ATIVA", flush=True)
            return None

        criando_cobranca = True

    try:
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

        print("========================================", flush=True)
        print("TENTANDO CRIAR NOVA COBRANCA", flush=True)
        print("TERMINAL:", TERMINAL_ID, flush=True)
        print("VALOR:", VALOR, flush=True)
        print("REFERENCIA:", referencia, flush=True)
        print("========================================", flush=True)

        requisicao = urllib.request.Request(
            API_ORDERS,
            data=corpo,
            headers={
                "Authorization": "Bearer " + token,
                "Content-Type": "application/json",
                "X-Idempotency-Key": str(uuid.uuid4())
            },
            method="POST"
        )

        with urllib.request.urlopen(requisicao, timeout=20) as resposta:
            resultado = resposta.read().decode("utf-8")

        resultado_json = json.loads(resultado)
        nova_ordem = resultado_json.get("id")

        if not nova_ordem:
            print("========================================", flush=True)
            print("ERRO: ORDER NAO RETORNOU ID", flush=True)
            print(resultado_json, flush=True)
            print("========================================", flush=True)
            return None

        with lock:
            ordem_atual = nova_ordem
            cobranca_criada = True

        print("========================================", flush=True)
        print("NOVA COBRANCA CRIADA", flush=True)
        print("ORDER:", nova_ordem, flush=True)
        print("VALOR: R$ 5,00", flush=True)
        print("========================================", flush=True)

        return resultado_json

    except urllib.error.HTTPError as erro:
        resposta = erro.read().decode("utf-8")

        print("========================================", flush=True)
        print("ERRO MERCADO PAGO AO CRIAR COBRANCA", flush=True)
        print("HTTP:", erro.code, flush=True)
        print("RESPOSTA:", resposta, flush=True)
        print("========================================", flush=True)

        return None

    except Exception as erro:
        print("========================================", flush=True)
        print("ERRO AO CRIAR COBRANCA:", str(erro), flush=True)
        print("========================================", flush=True)

        return None

    finally:
        with lock:
            criando_cobranca = False


def preparar_proxima_cobranca():
    global ordem_atual
    global cobranca_criada

    with lock:
        ordem_atual = None
        cobranca_criada = False

    print("PREPARANDO PROXIMA COBRANCA...", flush=True)

    time.sleep(ESPERA_PROXIMA_COBRANCA)

    criar_cobranca()


def monitorar_point():
    print("========================================", flush=True)
    print("MONITOR AUTOMATICO INICIADO", flush=True)
    print("========================================", flush=True)

    while True:
        try:
            with lock:
                order_id = ordem_atual
                ativa = cobranca_criada

            if not ativa or not order_id:
                print("Nenhuma cobrança ativa.", flush=True)

                criar_cobranca()

                time.sleep(INTERVALO_VERIFICACAO)
                continue

            dados = consultar_ordem(order_id)

            if not dados:
                time.sleep(INTERVALO_VERIFICACAO)
                continue

            status = dados.get("status")
            status_detail = dados.get("status_detail")

            print(
                "ORDER:",
                order_id,
                "| STATUS:",
                status,
                "| DETAIL:",
                status_detail,
                flush=True
            )

            if status == "processed":
                print("========================================", flush=True)
                print("PAGAMENTO PROCESSADO", flush=True)
                print("ORDER:", order_id, flush=True)
                print("========================================", flush=True)

                preparar_proxima_cobranca()
                continue

            if status == "canceled":
                print("========================================", flush=True)
                print("ORDER CANCELADA", flush=True)
                print("ORDER:", order_id, flush=True)
                print("========================================", flush=True)

                preparar_proxima_cobranca()
                continue

            if status == "failed":
                print("========================================", flush=True)
                print("ORDER FALHOU", flush=True)
                print("ORDER:", order_id, flush=True)
                print("========================================", flush=True)

                preparar_proxima_cobranca()
                continue

            if status == "expired":
                print("========================================", flush=True)
                print("ORDER EXPIRADA", flush=True)
                print("ORDER:", order_id, flush=True)
                print("========================================", flush=True)

                preparar_proxima_cobranca()
                continue

            if status == "at_terminal":
                print("Point aguardando finalizacao.", flush=True)

            time.sleep(INTERVALO_VERIFICACAO)

        except Exception as erro:
            print("========================================", flush=True)
            print("ERRO NO MONITOR:", str(erro), flush=True)
            print("========================================", flush=True)

            time.sleep(INTERVALO_VERIFICACAO)


@app.route("/webhook", methods=["POST"])
def webhook():
    global ultimo_webhook

    dados = request.get_json(silent=True) or {}

    data = dados.get("data", {})

    ultimo_webhook = {
        "tipo": dados.get("type"),
        "action": dados.get("action"),
        "data_id": data.get("id"),
        "recebido": dados
    }

    print("========================================", flush=True)
    print("WEBHOOK RECEBIDO", flush=True)
    print("TIPO:", dados.get("type"), flush=True)
    print("ACTION:", dados.get("action"), flush=True)
    print("DATA ID:", data.get("id"), flush=True)
    print("========================================", flush=True)

    return jsonify({"status": "ok"}), 200


@app.route("/iniciar", methods=["GET"])
def iniciar():
    with lock:
        if cobranca_criada and ordem_atual:
            return jsonify({
                "status": "ja_existe_cobranca",
                "ordem": ordem_atual
            }), 200

    resultado = criar_cobranca()

    if resultado:
        return jsonify({
            "status": "cobranca_criada",
            "mensagem": "Cobranca de R$ 5,00 criada na Point Pro 3",
            "mercado_pago": resultado
        }), 201

    return jsonify({
        "status": "erro",
        "mensagem": "Nao foi possivel criar a cobranca"
    }), 500


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
            "erro": "Nao foi possivel consultar a Order.",
            "order_id": order_id,
            "detalhe": "Veja os Logs do Render para identificar a resposta do Mercado Pago."
        }), 500

    pagamentos = dados.get(
        "transactions",
        {}
    ).get(
        "payments",
        []
    )

    return jsonify({
        "order_id": order_id,
        "status": dados.get("status"),
        "status_detail": dados.get("status_detail"),
        "payments": pagamentos
    }), 200


@app.route("/pagamento", methods=["GET"])
def pagamento():
    with lock:
        order_id = ordem_atual

    if not order_id:
        return jsonify({
            "status": "nenhuma_cobranca"
        }), 200

    dados = consultar_ordem(order_id)

    if not dados:
        return jsonify({
            "status": "erro_consulta"
        }), 200

    status = dados.get("status")

    return jsonify({
        "status_order": status,
        "ordem": order_id,
        "mensagem": "ESP32 sera acionado pelo botao fisico da impressao"
    }), 200


@app.route("/terminal", methods=["GET"])
def terminal():
    with lock:
        order_id = ordem_atual
        ativa = cobranca_criada
        criando = criando_cobranca

    return jsonify({
        "servidor": "online",
        "valor": VALOR,
        "terminal_id": TERMINAL_ID,
        "pos_id": POS_ID,
        "store_id": STORE_ID,
        "cobranca_criada": ativa,
        "criando_cobranca": criando,
        "ordem_atual": order_id,
        "modo_esp32": "botao_fisico_apos_impressao"
    }), 200


@app.route("/ultimo-webhook", methods=["GET"])
def ultimo_webhook_route():
    return jsonify(
        ultimo_webhook or {
            "status": "nenhum_webhook_recebido"
        }
    )


@app.route("/", methods=["GET"])
def pagina_inicial():
    return "Servidor Mercado Pago + ESP32 funcionando!"


def iniciar_monitor():
    thread = threading.Thread(
        target=monitorar_point,
        daemon=True
    )

    thread.start()


if __name__ == "__main__":
    iniciar_monitor()

    porta = int(
        os.environ.get(
            "PORT",
            "10000"
        )
    )

    app.run(
        host="0.0.0.0",
        port=porta
    )
```
