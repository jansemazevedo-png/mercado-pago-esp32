from flask import Flask, request, jsonify
import threading

app = Flask(__name__)

pagamento_aprovado = None
ids_processados = set()
lock = threading.Lock()


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

    print("===================================")
    print("WEBHOOK RECEBIDO")
    print("Tipo:", tipo)
    print("Action:", action)
    print("Data ID:", data_id)
    print("Dados:", dados)

    if tipo == "order" and data_id:

        data_id = str(data_id)

        with lock:

            if data_id in ids_processados:

                print("PAGAMENTO DUPLICADO IGNORADO!")
                print("ID JÁ PROCESSADO:", data_id)

            else:

                ids_processados.add(data_id)

                pagamento_aprovado = {
                    "id": data_id,
                    "status": "processado"
                }

                print("PAGAMENTO APROVADO!")
                print("ID DA ORDEM:", data_id)
                print("PAGAMENTO COLOCADO NA FILA PARA O ESP32.")

    else:

        print("WEBHOOK RECEBIDO, MAS NAO FOI ARMAZENADO.")

    print("===================================")

    return jsonify({"status": "ok"}), 200


@app.route("/pagamento", methods=["GET"])
def pagamento():
    global pagamento_aprovado

    with lock:

        if pagamento_aprovado:

            pagamento = pagamento_aprovado

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

@app.route("/terminal", methods=["GET"])
def terminal():
    return jsonify({
        "mensagem": "Rota de teste criada",
        "proximo_passo": "verificar Point Pro 3"
    }), 200
    
if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=10000
    )
