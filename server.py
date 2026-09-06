from flask import Flask, request, jsonify
import threading

app = Flask(**name**)

# ==========================================================

# PAGAMENTO AGUARDANDO O ESP32

# ==========================================================

pagamento_aprovado = None

# Guarda os IDs que já foram processados

ids_processados = set()

# Protege as variáveis contra acessos simultâneos

lock = threading.Lock()

# ==========================================================

# WEBHOOK DO MERCADO PAGO

# ==========================================================

@app.route("/webhook", methods=["POST"])
def webhook():
global pagamento_aprovado

```
# Lê o JSON enviado pelo Mercado Pago
dados = request.get_json(silent=True) or {}

# Lê também os parâmetros enviados na URL
data_id_url = request.args.get("data.id")
tipo_url = request.args.get("type")

# Dados enviados dentro do JSON
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

# ======================================================
# VERIFICA SE É UMA NOTIFICAÇÃO DE ORDER
# ======================================================

if tipo == "order" and data_id:

    data_id = str(data_id)

    with lock:

        # ==================================================
        # PROTEÇÃO CONTRA ID DUPLICADO
        # ==================================================

        if data_id in ids_processados:

            print("PAGAMENTO DUPLICADO IGNORADO!")
            print("ID JÁ PROCESSADO:", data_id)

        else:

            # Marca esse pagamento como processado
            ids_processados.add(data_id)

            # Coloca o pagamento para o ESP32 buscar
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
```

# ==========================================================

# ESP32 CONSULTA O PAGAMENTO

# ==========================================================

@app.route("/pagamento", methods=["GET"])
def pagamento():
global pagamento_aprovado

```
with lock:

    # Existe pagamento aguardando?
    if pagamento_aprovado:

        pagamento = pagamento_aprovado

        # Remove da fila imediatamente
        pagamento_aprovado = None

        print("PAGAMENTO ENTREGUE AO ESP32:")
        print(pagamento)

        return jsonify(pagamento), 200

print("Nenhum pagamento aguardando.")

return jsonify({
    "status": "nenhum_pagamento"
}), 200
```

# ==========================================================

# PÁGINA PRINCIPAL

# ==========================================================

@app.route("/", methods=["GET"])
def inicio():
return "Servidor Mercado Pago + ESP32 funcionando!"

# ==========================================================

# INICIALIZAÇÃO

# ==========================================================

if **name** == "**main**":
app.run(
host="0.0.0.0",
port=10000
)

