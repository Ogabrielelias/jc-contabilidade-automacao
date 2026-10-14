"""Cria somente a configuração inicial do PDF, sem alterar registros existentes."""

import sys
import tomllib
from pathlib import Path

from supabase import create_client

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from folha_config import CHAVE_CONFIG_PDF, config_pdf_inicial


def main():
    with (ROOT / ".streamlit" / "secrets.toml").open("rb") as arquivo:
        secrets = tomllib.load(arquivo)
    cliente = create_client(secrets["supabase_url"], secrets["supabase_key"])
    tabela = cliente.table("configuracoes_codigos")
    existente = tabela.select("chave").eq("chave", CHAVE_CONFIG_PDF).execute()
    if existente.data:
        print(f"Configuração {CHAVE_CONFIG_PDF} já existe; preservada.")
        return
    tabela.insert({"chave": CHAVE_CONFIG_PDF, "valor": config_pdf_inicial()}).execute()
    verificacao = tabela.select("chave").eq("chave", CHAVE_CONFIG_PDF).execute()
    if not verificacao.data:
        raise RuntimeError("Não foi possível confirmar a criação da configuração.")
    print(f"Configuração {CHAVE_CONFIG_PDF} criada e verificada.")


if __name__ == "__main__":
    main()
