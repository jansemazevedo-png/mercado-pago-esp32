```python
from flask import Flask, request, jsonify

app = Flask(__name__)

# Guarda temporariamente a última autorização recebida
pagamento_aprovado = None


@app.route("/webhook", methods=["POST"])
def webhook():
    global pagamento_aprovado

    # Dados enviados pelo Mercado Pago
    dados = request.get_json(silent=True)

    # Também pega os dados enviados na URL
    data_id = request.args.get("data.id")
    tipo = request.args.get("type")

    print("===================================")
    print("WEBHOOK RECEBIDO")
    print("Data ID:", data_id)
    print("Tipo:", tipo)
    print("Dados:", dados)

    # Verifica se é uma notificação de Order
    if tipo == "order":
        pagamento_aprovado = {
            "id": data_id,
            "status": "processado"
        }

        print("PAGAMENTO APROVADO!")
        print("ID DA ORDEM:", data_id)

    # Também aceita o formato JSON
    if dados and dados.get("action") == "order.processed":
        pagamento_aprovado = {
            "id": dados.get("data", {}).get("id"),
            "status": "processado"
        }

        print("PAGAMENTO APROVADO!")
        print("ID DA ORDEM:", pagamento_aprovado["id"])

    print("===================================")

    return jsonify({"status": "ok"}), 200


@app.route("/pagamento", methods=["GET"])
def pagamento():
    # Endpoint que futuramente será consultado pelo ESP32
    if pagamento_aprovado:
        return jsonify(pagamento_aprovado), 200

    return jsonify({
        "status": "nenhum_pagamento"
    }), 200


@app.route("/", methods=["GET"])
def inicio():
    return "Servidor Mercado Pago + ESP32 funcionando!"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
```
