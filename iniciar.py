"""Instala e inicia o Buscador de Autopeças com um só comando.

Na primeira vez:
  1. cria um ambiente Python isolado na pasta .venv
  2. instala as bibliotecas necessárias
  3. pede as chaves (SerpAPI e Anthropic) e grava no arquivo .env
Depois: inicia o servidor e abre o navegador em http://localhost:8000

Para trocar as chaves depois, rode:  iniciar.py --configurar
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import venv
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
ENV_FILE = ROOT / ".env"
STAMP = VENV / ".instalado"
PORT = int(os.environ.get("PORTA", "8000"))


def say(msg: str = "") -> None:
    print(msg, flush=True)


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def install() -> None:
    req = ROOT / "requirements.txt"
    if STAMP.exists() and STAMP.stat().st_mtime >= req.stat().st_mtime:
        return
    if not venv_python().exists():
        say("[1/3] Criando o ambiente do programa (só na primeira vez)...")
        venv.create(VENV, with_pip=True)
    say("[2/3] Baixando e instalando as bibliotecas (pode levar alguns minutos)...")
    py = str(venv_python())
    subprocess.check_call([py, "-m", "pip", "install", "--disable-pip-version-check", "-q", "--upgrade", "pip"])
    subprocess.check_call([py, "-m", "pip", "install", "--disable-pip-version-check", "-q", "-r", str(req)])
    STAMP.write_text("ok")
    say("      Bibliotecas instaladas.")


def read_env() -> dict[str, str]:
    values: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip()
    return values


def ask(label: str, current: str, help_text: str) -> str:
    say()
    say(label)
    say(help_text)
    shown = f" [atual: ...{current[-4:]}]" if current else ""
    answer = input(f"Cole aqui e tecle Enter (Enter vazio = {'manter' if current else 'pular'}){shown}: ").strip()
    return answer or current


def configure(force: bool = False) -> None:
    values = read_env()
    has_search = values.get("SERPAPI_KEY") or (values.get("GOOGLE_CSE_KEY") and values.get("GOOGLE_CSE_CX"))
    if has_search and not force:
        return
    say()
    say("[3/3] Configuração das chaves")
    say("As chaves ficam somente no arquivo .env, neste computador.")
    values["SERPAPI_KEY"] = ask(
        "1) Chave da SerpAPI (pesquisa no Google) — OBRIGATÓRIA",
        values.get("SERPAPI_KEY", ""),
        "   Crie a conta em https://serpapi.com e copie a 'API Key' do painel.")
    values["ANTHROPIC_API_KEY"] = ask(
        "2) Chave da Anthropic (IA para classificar fabricantes) — OPCIONAL",
        values.get("ANTHROPIC_API_KEY", ""),
        "   Em https://console.anthropic.com > API Keys. Sem ela, os preços funcionam normalmente.")
    values.setdefault("AI_MODEL", "claude-opus-5-5")
    values.setdefault("AI_EFFORT", "medium")
    lines = ["# Gerado por iniciar.py. Não compartilhe este arquivo.",
             *(f"{k}={v}" for k, v in values.items())]
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if not values["SERPAPI_KEY"]:
        say()
        say("ATENÇÃO: sem a chave da SerpAPI o programa abre, mas não consegue pesquisar.")
        say("Rode de novo com --configurar quando tiver a chave.")


def run_server() -> None:
    url = f"http://localhost:{PORT}"
    say()
    say("=" * 60)
    say(f" Buscador de Autopeças rodando em {url}")
    say(" O navegador vai abrir sozinho. Para ENCERRAR, feche esta janela")
    say(" ou tecle Ctrl+C.")
    say("=" * 60)
    threading.Timer(2.5, lambda: webbrowser.open(url)).start()
    try:
        subprocess.call([str(venv_python()), "-m", "uvicorn", "app.main:app",
                         "--host", "127.0.0.1", "--port", str(PORT)], cwd=ROOT)
    except KeyboardInterrupt:
        pass


def main() -> int:
    if sys.version_info < (3, 10):
        say("É preciso o Python 3.10 ou mais novo. Baixe em https://www.python.org/downloads/")
        return 1
    os.chdir(ROOT)
    try:
        install()
    except subprocess.CalledProcessError:
        say()
        say("Não foi possível instalar as bibliotecas. Verifique a conexão com a internet e tente de novo.")
        return 1
    configure(force="--configurar" in sys.argv)
    if "--so-instalar" in sys.argv:
        return 0
    run_server()
    return 0


if __name__ == "__main__":
    code = main()
    if code and os.name == "nt":
        input("Tecle Enter para fechar.")
    sys.exit(code)
