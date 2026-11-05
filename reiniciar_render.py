import os
import urllib.request
import urllib.error

SERVICE_ID = "srv-dael1967bikc73dn3dhg"
API_KEY = os.environ.get("RENDER_API_KEY")

if not API_KEY:
    raise RuntimeError("RENDER_API_KEY não configurada")

url = f"https://api.render.com/v1/services/{SERVICE_ID}/restart"

req = urllib.request.Request(
    url,
    method="POST",
    headers={
        "Authorization": f"Bearer {API_KEY}",
        "Accept": "application/json"
    }
)

try:
    with urllib.request.urlopen(req, timeout=30) as response:
        print("Resposta do Render:", response.status)
        print("Reinicialização solicitada.")
except urllib.error.HTTPError as e:
    print("Erro HTTP:", e.code)
    print(e.read().decode())
    raise
