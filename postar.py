"""Postagem diária automática no Instagram — Euler Ramos de Oliveira, Consultor de Seguros e Benefícios.

Publica a arte do dia (rodízio segunda→domingo) no Feed e nos Stories pela
API do Instagram com login do Instagram (graph.instagram.com).

Uso:
    python postar.py                 # simulação: mostra o que seria postado, não posta nada
    python postar.py --publicar      # posta de verdade (Feed + Stories)
    python postar.py --publicar --so-stories
    python postar.py --arte auto     # força uma arte específica
    python postar.py --renovar-token # renova o token (vale 60 dias; renovar antes de vencer)

Configuração em .env (mesma pasta) ou variáveis de ambiente:
    IG_ACCESS_TOKEN   token gerado no painel da Meta (NUNCA compartilhar)
    PUBLIC_BASE_URL   endereço público onde estão as imagens .jpg (ex.: https://.../artes)
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://graph.instagram.com/v23.0"
AQUI = Path(__file__).resolve().parent
ENV = AQUI / ".env"
LOG = AQUI / "postagens.log"

# segunda=0 … domingo=6
RODIZIO = ["geral", "auto", "residencial", "empresarial", "solar", "saude", "vida"]


def carregar_env():
    if ENV.exists():
        for linha in ENV.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if linha and not linha.startswith("#") and "=" in linha:
                k, v = linha.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def salvar_env(chave, valor):
    texto = ENV.read_text(encoding="utf-8") if ENV.exists() else ""
    if re.search(rf"^{chave}=.*$", texto, re.M):
        texto = re.sub(rf"^{chave}=.*$", f"{chave}={valor}", texto, flags=re.M)
    else:
        texto += f"\n{chave}={valor}\n"
    ENV.write_text(texto, encoding="utf-8")


def legendas():
    md = (AQUI / "legendas.md").read_text(encoding="utf-8")
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"^## (\w+)\n(.*?)(?=^## |\Z)", md, re.S | re.M)}


def chamar(metodo, caminho, **params):
    params["access_token"] = os.environ["IG_ACCESS_TOKEN"]
    dados = urllib.parse.urlencode(params).encode()
    url = f"{API}/{caminho}"
    if metodo == "GET":
        req = urllib.request.Request(f"{url}?{dados.decode()}")
    else:
        req = urllib.request.Request(url, data=dados, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        corpo = e.read().decode(errors="replace")
        raise SystemExit(f"Erro da API ({e.code}) em {caminho}: {corpo}")


def registrar(msg):
    linha = f"{dt.datetime.now():%Y-%m-%d %H:%M} {msg}"
    print(linha)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(linha + "\n")


def publicar(ig_id, image_url, caption=None, stories=False):
    params = {"image_url": image_url}
    if stories:
        params["media_type"] = "STORIES"
    else:
        params["caption"] = caption
    container = chamar("POST", f"{ig_id}/media", **params)["id"]
    for _ in range(30):  # aguarda o Instagram processar a imagem
        status = chamar("GET", container, fields="status_code").get("status_code")
        if status == "FINISHED":
            break
        if status == "ERROR":
            raise SystemExit(f"Instagram recusou a imagem {image_url}")
        time.sleep(5)
    return chamar("POST", f"{ig_id}/media_publish", creation_id=container)["id"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--publicar", action="store_true", help="posta de verdade (sem isso é só simulação)")
    ap.add_argument("--so-stories", action="store_true")
    ap.add_argument("--so-feed", action="store_true")
    ap.add_argument("--arte", choices=RODIZIO)
    ap.add_argument("--renovar-token", action="store_true")
    args = ap.parse_args()
    carregar_env()

    if not os.environ.get("IG_ACCESS_TOKEN"):
        sys.exit("Falta IG_ACCESS_TOKEN no arquivo .env")

    if args.renovar_token:
        r = urllib.request.urlopen(f"https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token&access_token={os.environ['IG_ACCESS_TOKEN']}")
        novo = json.load(r)
        if not os.environ.get("GITHUB_ACTIONS"):
            salvar_env("IG_ACCESS_TOKEN", novo["access_token"])
        registrar(f"token renovado, vale mais {novo['expires_in'] // 86400} dias")
        return

    base = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
    if not base:
        sys.exit("Falta PUBLIC_BASE_URL no arquivo .env")

    arte = args.arte or RODIZIO[dt.date.today().weekday()]
    url = f"{base}/{arte}.jpg"
    caption = legendas()[arte]
    conta = chamar("GET", "me", fields="user_id,username")
    ig_id = conta["user_id"]

    print(f"Conta: @{conta['username']}  |  Arte do dia: {arte}  |  {url}")
    if not args.publicar:
        print("\n--- SIMULAÇÃO (nada foi postado). Legenda: ---\n" + caption)
        return

    if not args.so_stories:
        registrar(f"FEED    @{conta['username']} {arte} -> post {publicar(ig_id, url, caption)}")
    if not args.so_feed:
        registrar(f"STORIES @{conta['username']} {arte} -> story {publicar(ig_id, url, stories=True)}")


if __name__ == "__main__":
    main()
