#!/bin/zsh
cd "$(dirname "$0")" || exit 1
if [[ ! -x .venv/bin/python ]]; then
  echo "First follow the setup steps in README.md to create .venv and install dependencies."
  read -r "reply?Press Return to close."
  exit 1
fi
exec .venv/bin/python -m streamlit run app.py --server.address 127.0.0.1
