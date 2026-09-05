from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/webhook", methods=["POST"])
def webhook():
    dados = request.get_json(silent=True)

    print("Webhook recebido:")
    print(dados)

    if dados and dados.get("action") == "order.processed":
        print("PAGAMENTO APROVADO!")

        # Aqui, futuramente, vamos mandar a autorização para o ESP32.

    return jsonify({"status": "ok"}), 200

@app.route("/", methods=["GET"])
def inicio():
    return "Servidor Mercado Pago + ESP32 funcionando!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
