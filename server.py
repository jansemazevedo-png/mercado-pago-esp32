
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
# CONFIGURACAO
# ==========================================

VALOR = "5.00"

TERMINAL_ID = "PAX_Q92__Q92-1734118066"
STORE_ID = "77202273"
POS_ID = "137651952"

API_ORDERS = "https://api.mercadopago.com/v1/orders"

INTERVALO_VERIFICACAO = 15
ESPERA_PROXIMA_COBRANCA = 5
ESPERA_FALHA_CRIACAO = 60
ESPERA_FALHA_CONSULTA = 30

# ==========================================
# ESTADO DO PROGRAMA
# ==========================================

lock = threading.Lock()

ordem_atual = None
status_order_atual = None
cobranca_criada = False
criando_cobranca = False

ultimo_webhook = None

# Reutilizados se uma tentativa precisar ser repetida.
chave_idempotencia_pendente = None
dados_cobranca_pendente = None
referencia_pendente = None

proxima_tentativa_cobranca = 0
monitor_iniciado = False


# ==========================================
# CONSULTAR UMA ORDER
# ==========================================

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
            conteudo = resposta.read().decode("utf-8")

        return json.loads(conteudo)

    except urllib.error.HTTPError as erro:
        resposta = erro.read().decode("utf-8", errors="replace")

        print(
            "ERRO CONSULTANDO ORDER:",
            order_id,
            "| HTTP:",
            erro.code,
            "| RESPOSTA:",
            resposta,
            flush=True
        )
        return None

    except Exception as erro:
        print("ERRO CONSULTANDO ORDER:", str(erro), flush=True)
        return None


# ==========================================
# CRIAR COBRANCA
# ==========================================

def criar_cobranca():
    global ordem_atual
    global status_order_atual
    global cobranca_criada
    global criando_cobranca
    global chave_idempotencia_pendente
    global dados_cobranca_pendente
    global referencia_pendente
    global proxima_tentativa_cobranca

    token = os.environ.get("MP_ACCESS_TOKEN")

    if not token:
        print("ERRO: MP_ACCESS_TOKEN NAO CONFIGURADO", flush=True)
        return None

    with lock:
        if criando_cobranca:
            print("JA EXISTE UMA COBRANCA SENDO CRIADA", flush=True)
            return None

        if cobranca_criada and ordem_atual:
            print("JA EXISTE UMA COBRANCA REGISTRADA", flush=True)
            return None

        if time.time() < proxima_tentativa_cobranca:
            print("AGUARDANDO INTERVALO PARA NOVA TENTATIVA", flush=True)
            return None

        if chave_idempotencia_pendente is None:
            referencia_pendente = "auto-r5-" + uuid.uuid4().hex[:12]

            dados_cobranca_pendente = {
                "type": "point",
                "external_reference": referencia_pendente,
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

            chave_idempotencia_pendente = str(uuid.uuid4())

        # Guardar os dados da tentativa antes da requisicao.
        chave = chave_idempotencia_pendente
        dados = dados_cobranca_pendente
        referencia = referencia_pendente
        criando_cobranca = True

    try:
        corpo = json.dumps(dados).encode("utf-8")

        print("========================================", flush=True)
        print("TENTANDO CRIAR COBRANCA", flush=True)
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
                "X-Idempotency-Key": chave
            },
            method="POST"
        )

        with urllib.request.urlopen(requisicao, timeout=20) as resposta:
            resultado = resposta.read().decode("utf-8")

        resultado_json = json.loads(resultado)
        nova_ordem = resultado_json.get("id")

        if not nova_ordem:
            print("ERRO: ORDER NAO RETORNOU ID", flush=True)

            with lock:
                proxima_tentativa_cobranca = (
                    time.time() + ESPERA_FALHA_CRIACAO
                )

            return None

        with lock:
            ordem_atual = nova_ordem
            status_order_atual = resultado_json.get("status", "created")
            cobranca_criada = True

            chave_idempotencia_pendente = None
            dados_cobranca_pendente = None
            referencia_pendente = None
            proxima_tentativa_cobranca = 0

        print("========================================", flush=True)
        print("NOVA COBRANCA CRIADA", flush=True)
        print("ORDER:", nova_ordem, flush=True)
        print("VALOR: R$ 5,00", flush=True)
        print("========================================", flush=True)

        return resultado_json

    except urllib.error.HTTPError as erro:
        resposta = erro.read().decode("utf-8", errors="replace")

        print("ERRO MERCADO PAGO AO CRIAR COBRANCA", flush=True)
        print("HTTP:", erro.code, flush=True)
        print("RESPOSTA:", resposta, flush=True)

        with lock:
            proxima_tentativa_cobranca = (
                time.time() + ESPERA_FALHA_CRIACAO
            )

            # Para erros de limite ou do servidor, preservar a mesma
            # chave e o mesmo corpo para uma eventual repeticao.
            # Para outros erros HTTP, a resposta indica rejeicao.
            if erro.code != 429 and erro.code < 500:
                chave_idempotencia_pendente = None
                dados_cobranca_pendente = None
                referencia_pendente = None

        return None

    except Exception as erro:
        print("ERRO AO CRIAR COBRANCA:", str(erro), flush=True)

        with lock:
            # A requisicao pode ter chegado ao Mercado Pago mesmo
            # sem o servidor receber a resposta. Preservar a chave.
            proxima_tentativa_cobranca = (
                time.time() + ESPERA_FALHA_CRIACAO
            )

        return None

    finally:
        with lock:
            criando_cobranca = False


# ==========================================
# PREPARAR A PROXIMA COBRANCA
# ==========================================

def preparar_proxima_cobranca():
    global ordem_atual
    global status_order_atual
    global cobranca_criada

    with lock:
        ordem_atual = None
        status_order_atual = None
        cobranca_criada = False

    print("PREPARANDO PROXIMA COBRANCA...", flush=True)

    time.sleep(ESPERA_PROXIMA_COBRANCA)

    criar_cobranca()


# ==========================================
# MONITOR AUTOMATICO DA POINT
# ==========================================

def monitorar_point():
    global status_order_atual

    print("MONITOR AUTOMATICO INICIADO", flush=True)

    while True:
        try:
            with lock:
                order_id = ordem_atual
                ativa = cobranca_criada

            if not ativa or not order_id:
                criar_cobranca()
                time.sleep(INTERVALO_VERIFICACAO)
                continue

            dados = consultar_ordem(order_id)

            if not dados:
                print(
                    "CONSULTA FALHOU. AGUARDANDO",
                    ESPERA_FALHA_CONSULTA,
                    "SEGUNDOS.",
                    flush=True
                )
                time.sleep(ESPERA_FALHA_CONSULTA)
                continue

            status = dados.get("status")
            status_detail = dados.get("status_detail")

            with lock:
                status_order_atual = status

            print(
                "ORDER:", order_id,
                "| STATUS:", status,
                "| DETAIL:", status_detail,
                flush=True
            )

            if status in ("processed", "canceled", "failed", "expired"):
                print("ORDER FINALIZADA:", status, flush=True)
                preparar_proxima_cobranca()
                continue

            if status == "at_terminal":
                print("POINT AGUARDANDO FINALIZACAO.", flush=True)

            time.sleep(INTERVALO_VERIFICACAO)

        except Exception as erro:
            print("ERRO NO MONITOR:", str(erro), flush=True)
            time.sleep(INTERVALO_VERIFICACAO)


# ==========================================
# TESTAR TOKEN
# ==========================================

@app.route("/teste-token", methods=["GET"])
def teste_token():
    token = os.environ.get("MP_ACCESS_TOKEN")

    if not token:
        return jsonify({
            "status": "ERRO",
            "mensagem": "MP_ACCESS_TOKEN nao encontrado no Render"
        }), 500

    requisicao = urllib.request.Request(
        "https://api.mercadolibre.com/users/me",
        headers={"Authorization": "Bearer " + token},
        method="GET"
    )

    try:
        with urllib.request.urlopen(requisicao, timeout=15) as resposta:
            resultado = json.loads(
                resposta.read().decode("utf-8")
            )

        return jsonify({
            "status": "TOKEN_VALIDO",
            "http": 200,
            "usuario_id": resultado.get("id"),
            "nickname": resultado.get("nickname")
        }), 200

    except urllib.error.HTTPError as erro:
        resposta = erro.read().decode("utf-8", errors="replace")

        return jsonify({
            "status": "TOKEN_REJEITADO",
            "http": erro.code,
            "resposta": resposta
        }), erro.code

    except Exception as erro:
        return jsonify({
            "status": "ERRO",
            "mensagem": str(erro)
        }), 500


# ==========================================
# WEBHOOK
# ==========================================

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

    print(
        "WEBHOOK RECEBIDO:",
        dados.get("type"),
        dados.get("action"),
        data.get("id"),
        flush=True
    )

    return jsonify({"status": "ok"}), 200


# ==========================================
# INICIAR COBRANCA MANUALMENTE
# ==========================================

@app.route("/iniciar", methods=["GET"])
def iniciar():
    with lock:
        if cobranca_criada and ordem_atual:
            return jsonify({
                "status": "ja_existe_cobranca",
                "ordem": ordem_atual
            }), 200

        if criando_cobranca:
            return jsonify({
                "status": "criando_cobranca"
            }), 200

        if time.time() < proxima_tentativa_cobranca:
            return jsonify({
                "status": "aguardando_nova_tentativa"
            }), 429

    resultado = criar_cobranca()

    if resultado:
        return jsonify({
            "status": "cobranca_criada",
            "mensagem": "Cobranca de R$ 5,00 criada na Point Pro 3",
            "mercado_pago": resultado
        }), 201

    return jsonify({
        "status": "erro",
        "mensagem": "Nao foi possivel criar a cobranca. Consulte os Logs do Render."
    }), 500


# ==========================================
# CONSULTAR ORDER MANUALMENTE
# Esta rota faz uma chamada a API por acesso.
# ==========================================

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
            "detalhe": "Consulte os Logs do Render."
        }), 500

    pagamentos = dados.get(
        "transactions", {}
    ).get(
        "payments", []
    )

    return jsonify({
        "order_id": order_id,
        "status": dados.get("status"),
        "status_detail": dados.get("status_detail"),
        "payments": pagamentos
    }), 200


# ==========================================
# STATUS PARA O ESP32
# Nao consulta a API a cada acesso.
# ==========================================

@app.route("/pagamento", methods=["GET"])
def pagamento():
    with lock:
        order_id = ordem_atual
        status = status_order_atual

    if not order_id:
        return jsonify({
            "status": "nenhuma_cobranca"
        }), 200

    return jsonify({
        "status_order": status or "desconhecido",
        "ordem": order_id,
        "mensagem": "ESP32 sera acionado pelo botao fisico da impressao"
    }), 200


# ==========================================
# STATUS GERAL DO TERMINAL
# ==========================================

@app.route("/terminal", methods=["GET"])
def terminal():
    with lock:
        order_id = ordem_atual
        ativa = cobranca_criada
        criando = criando_cobranca
        status = status_order_atual

    return jsonify({
        "servidor": "online",
        "valor": VALOR,
        "terminal_id": TERMINAL_ID,
        "pos_id": POS_ID,
        "store_id": STORE_ID,
        "cobranca_criada": ativa,
        "criando_cobranca": criando,
        "ordem_atual": order_id,
        "status_order": status,
        "modo_esp32": "botao_fisico_apos_impressao"
    }), 200


# ==========================================
# ULTIMO WEBHOOK RECEBIDO
# ==========================================

@app.route("/ultimo-webhook", methods=["GET"])
def ultimo_webhook_route():
    with lock:
        resultado = ultimo_webhook

    return jsonify(
        resultado or {
            "status": "nenhum_webhook_recebido"
        }
    ), 200


# ==========================================
# PAGINA INICIAL
# ==========================================

@app.route("/", methods=["GET"])
def pagina_inicial():
    return "Servidor Mercado Pago + ESP32 funcionando!"


# ==========================================
# INICIAR SERVIDOR
# ==========================================

def iniciar_monitor():
    global monitor_iniciado

    with lock:
        if monitor_iniciado:
            return

        monitor_iniciado = True

    thread = threading.Thread(
        target=monitorar_point,
        daemon=True
    )
    thread.start()


if __name__ == "__main__":
    iniciar_monitor()

    porta = int(os.environ.get("PORT", "10000"))

    app.run(
        host="0.0.0.0",
        port=porta
    )
