#!/bin/bash
# Mac: dê dois cliques neste arquivo para instalar e iniciar o buscador.
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "O Python não está instalado. Baixe em https://www.python.org/downloads/"
  open "https://www.python.org/downloads/"
  read -p "Tecle Enter para fechar."
  exit 1
fi
python3 iniciar.py "$@"
