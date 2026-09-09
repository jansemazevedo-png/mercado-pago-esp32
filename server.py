from flask import Flask, request, jsonify
import os
import json
import uuid
import urllib.request
import urllib.error
import threading
import time

app = Flask(__name__)

# ==========================================
# CONFIGURAÇÃO
# ==========================================

VALOR = "5.00"

TERMINAL_ID = "PAX_Q92__Q92-1734118066""
STORE_ID = "77202273"
POS_ID = "137651952"

API_ORDERS = "https://api.mercadopago.com/v1/orders"

INTERVALO_VERIFICACAO = 3
ESPERA_PROXIMA_COBRANCA = 3

# ==========================================
# VARIÁVEIS
# ==========================================

lock = threading.Lock()

ordem_atual = None
cobranca_criada = False
criando_cobranca = False

ultimo_webhook = None


# ==========================================
# CONSULTAR ORDER
# ==========================================

def consultar_ordem(order_id):

    token = os.environ.get("MP_ACCESS_TOKEN")

    if not token:
        print("ERRO: MP_ACCESS_TOKEN NAO CONFIGURADO")
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


# ==========================================
# CRIAR COBRANÇA
# ==========================================

def criar_cobranca():

    global ordem_atual
    global cobranca_criada
    global criando_cobranca

    token = os.environ.get("MP_ACCESS_TOKEN")

    if not token:

        print("ERRO: MP_ACCESS_TOKEN NAO CONFIGURADO")
        return None

    with lock:

        if criando_cobranca:

            print("JA EXISTE UMA COBRANCA SENDO CRIADA")
            return None

        if cobranca_criada and ordem_atual:

            print("JA EXISTE UMA COBRANCA ATIVA")
            return None

        criando_cobranca = True

    try:

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

        corpo = json.dumps(
            dados
        ).encode("utf-8")

        requisicao = urllib.request.Request(

            API_ORDERS,

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

        with urllib.request.urlopen(
            requisicao,
            timeout=20
        ) as resposta:

            resultado = resposta.read().decode(
                "utf-8"
            )

        resultado_json = json.loads(
            resultado
        )

        nova_ordem = resultado_json.get(
            "id"
        )

        if not nova_ordem:

            print("ERRO: ORDER NAO RETORNOU ID")
            print(resultado_json)

            return None

        with lock:

            ordem_atual = nova_ordem
            cobranca_criada = True

        print("========================================")
        print("NOVA COBRANCA CRIADA")
        print("ORDER:", nova_ordem)
        print("VALOR: R$ 5,00")
        print("========================================")

        return resultado_json

    except urllib.error.HTTPError as erro:

        resposta = erro.read().decode(
            "utf-8"
        )

        print("ERRO MERCADO PAGO")
        print("HTTP:", erro.code)
        print(resposta)

        return None

    except Exception as erro:

        print("ERRO AO CRIAR COBRANCA:", erro)

        return None

    finally:

        with lock:
            criando_cobranca = False


# ==========================================
# PREPARAR PRÓXIMA COBRANÇA
# ==========================================

def preparar_proxima_cobranca():

    global ordem_atual
    global cobranca_criada

    with lock:

        ordem_atual = None
        cobranca_criada = False

    time.sleep(
        ESPERA_PROXIMA_COBRANCA
    )

    criar_cobranca()


# ==========================================
# MONITOR AUTOMÁTICO DA POINT
# ==========================================

def monitorar_point():

    print("========================================")
    print("MONITOR AUTOMATICO INICIADO")
    print("========================================")

    while True:

        try:

            with lock:

                order_id = ordem_atual
                ativa = cobranca_criada

            # ----------------------------------
            # SE NÃO EXISTE COBRANÇA
            # ----------------------------------

            if not ativa or not order_id:

                print(
                    "Nenhuma cobrança ativa."
                )

                criar_cobranca()

                time.sleep(
                    INTERVALO_VERIFICACAO
                )

                continue

            # ----------------------------------
            # CONSULTAR ORDER
            # ----------------------------------

            dados = consultar_ordem(
                order_id
            )

            if not dados:

                time.sleep(
                    INTERVALO_VERIFICACAO
                )

                continue

            status = dados.get(
                "status"
            )

            status_detail = dados.get(
                "status_detail"
            )

            print(
                "ORDER:",
                order_id,
                "| STATUS:",
                status,
                "| DETAIL:",
                status_detail
            )

            # ----------------------------------
            # PAGAMENTO PROCESSADO
            # ----------------------------------

            if status == "processed":

                print("========================================")
                print("PAGAMENTO PROCESSADO")
                print("ORDER:", order_id)
                print("========================================")

                preparar_proxima_cobranca()

                continue

            # ----------------------------------
            # COBRANÇA CANCELADA
            # ----------------------------------

            if status == "canceled":

                print("========================================")
                print("ORDER CANCELADA")
                print("ORDER:", order_id)
                print("========================================")

                preparar_proxima_cobranca()

                continue

            # ----------------------------------
            # COBRANÇA FALHOU
            # ----------------------------------

            if status == "failed":

                print("========================================")
                print("ORDER FALHOU")
                print("ORDER:", order_id)
                print("========================================")

                preparar_proxima_cobranca()

                continue

            # ----------------------------------
            # COBRANÇA EXPIRADA
            # ----------------------------------

            if status == "expired":

                print("========================================")
                print("ORDER EXPIRADA")
                print("ORDER:", order_id)
                print("========================================")

                preparar_proxima_cobranca()

                continue

            # ----------------------------------
            # AT TERMINAL
            # ----------------------------------

            if status == "at_terminal":

                print(
                    "Point aguardando finalizacao."
                )

            time.sleep(
                INTERVALO_VERIFICACAO
            )

        except Exception as erro:

            print(
                "ERRO NO MONITOR:",
                erro
            )

            time.sleep(
                INTERVALO_VERIFICACAO
            )


# ==========================================
# WEBHOOK
# ==========================================

@app.route(
    "/webhook",
    methods=["POST"]
)
def webhook():

    global ultimo_webhook

    dados = request.get_json(
        silent=True
    ) or {}

    data = dados.get(
        "data",
        {}
    )

    ultimo_webhook = {

        "tipo":
            dados.get("type"),

        "action":
            dados.get("action"),

        "data_id":
            data.get("id"),

        "recebido":
            dados

    }

    print("========================================")
    print("WEBHOOK RECEBIDO")
    print("TIPO:", dados.get("type"))
    print("ACTION:", dados.get("action"))
    print("DATA ID:", data.get("id"))
    print("========================================")

    return jsonify({
        "status": "ok"
    }), 200


# ==========================================
# INICIAR COBRANÇA MANUAL
# ==========================================

@app.route(
    "/iniciar",
    methods=["GET"]
)
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


# ==========================================
# STATUS DA ORDER
# ==========================================

@app.route(
    "/status-order",
    methods=["GET"]
)
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


# ==========================================
# /PAGAMENTO
# MANTIDO APENAS POR COMPATIBILIDADE
# ==========================================

@app.route(
    "/pagamento",
    methods=["GET"]
)
def pagamento():

    with lock:

        order_id = ordem_atual

    if not order_id:

        return jsonify({

            "status":
                "nenhuma_cobranca"

        }), 200

    dados = consultar_ordem(
        order_id
    )

    if not dados:

        return jsonify({

            "status":
                "erro_consulta"

        }), 200

    status = dados.get(
        "status"
    )

    return jsonify({

        "status_order":
            status,

        "ordem":
            order_id,

        "mensagem":
            "ESP32 sera acionado pelo botao fisico da impressao"

    }), 200


# ==========================================
# STATUS DO SERVIDOR
# ==========================================

@app.route(
    "/terminal",
    methods=["GET"]
)
def terminal():

    with lock:

        order_id = ordem_atual
        ativa = cobranca_criada
        criando = criando_cobranca

    return jsonify({

        "servidor":
            "online",

        "valor":
            VALOR,

        "terminal_id":
            TERMINAL_ID,

        "pos_id":
            POS_ID,

        "store_id":
            STORE_ID,

        "cobranca_criada":
            ativa,

        "criando_cobranca":
            criando,

        "ordem_atual":
            order_id,

        "modo_esp32":
            "botao_fisico_apos_impressao"

    }), 200


# ==========================================
# ÚLTIMO WEBHOOK
# ==========================================

@app.route(
    "/ultimo-webhook",
    methods=["GET"]
)
def ultimo_webhook_route():

    return jsonify(
        ultimo_webhook or {
            "status":
                "nenhum_webhook_recebido"
        }
    ), 200


# ==========================================
# PÁGINA INICIAL
# ==========================================

@app.route(
    "/",
    methods=["GET"]
)
def pagina_inicial():

    return (
        "Servidor Mercado Pago + ESP32 funcionando!"
    )


# ==========================================
# INICIAR MONITOR
# ==========================================

def iniciar_monitor():

    thread = threading.Thread(
        target=monitorar_point,
        daemon=True
    )

    thread.start()


# ==========================================
# EXECUÇÃO
# ==========================================

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
