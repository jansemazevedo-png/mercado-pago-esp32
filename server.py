from flask import Flask, request, jsonify
import threading

app = Flask(__name__)

# Guarda temporariamente o último pagamento aprovado
pagamento_aprovado = None

# Evita problemas se chegarem várias notificações ao mesmo tempo
lock = threading.Lock()


@app.route("/webhook", methods=["POST"])
def webhook():
    global pagamento_aprovado

    # Lê o JSON enviado pelo Mercado Pago
    dados = request.get_json(silent=True) or {}

    # Lê também os parâmetros enviados na URL
    data_id_url = request.args.get("data.id")
    tipo_url = request.args.get("type")

    # Pega os dados do JSON
    tipo_json = dados.get("type")
    action = dados.get("action")

    data = dados.get("data", {})
    data_id_json = data.get("id")

    # Usa o ID que estiver disponível
    data_id = data_id_url or data_id_json
    tipo = tipo_url or tipo_json

    print("===================================")
    print("WEBHOOK RECEBIDO")
    print("Tipo:", tipo)
    print("Action:", action)
    print("Data ID:", data_id)
    print("Dados:", dados)

    # Verifica se é uma notificação de Order
    if tipo == "order" and data_id:

        with lock:
            pagamento_aprovado = {
                "id": str(data_id),
                "status": "processado"
            }

        print("PAGAMENTO APROVADO!")
        print("ID DA ORDEM:", data_id)

    else:
        print("WEBHOOK RECEBIDO, MAS NAO FOI ARMAZENADO.")

    print("===================================")

    return jsonify({"status": "ok"}), 200


@app.route("/pagamento", methods=["GET"])
def pagamento():
    global pagamento_aprovado

    with lock:

        # Se existe pagamento aguardando
        if pagamento_aprovado:

            pagamento = pagamento_aprovado

            # Remove imediatamente para não executar duas vezes
            pagamento_aprovado = None

            print("PAGAMENTO ENTREGUE AO ESP32:")
            print(pagamento)

            return jsonify(pagamento), 200

    print("Nenhum pagamento aguardando.")

    return jsonify({
        "status": "nenhum_pagamento"
    }), 200


@app.route("/", methods=["GET"])
def inicio():
    return "Servidor Mercado Pago + ESP32 funcionando!"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
