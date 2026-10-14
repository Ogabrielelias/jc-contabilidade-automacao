"""Aplica os grupos solicitados, preservando os demais campos da configuração."""

import sys
import tomllib
from copy import deepcopy
from pathlib import Path

from supabase import create_client

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from folha_config import CHAVE_CONFIG_PDF, CODIGOS_PADRAO_PDF, config_pdf_inicial


def main():
    with (ROOT / ".streamlit" / "secrets.toml").open("rb") as arquivo:
        secrets = tomllib.load(arquivo)
    cliente = create_client(secrets["supabase_url"], secrets["supabase_key"])
    tabela = cliente.table("configuracoes_codigos")
    resposta = tabela.select("valor").eq("chave", CHAVE_CONFIG_PDF).execute()
    config = deepcopy(resposta.data[0]["valor"]) if resposta.data else config_pdf_inicial()
    grupos = config.setdefault("colunas_especiais", {})
    for coluna, codigos in CODIGOS_PADRAO_PDF.items():
        grupos[coluna] = [str(codigo).zfill(8) for codigo in codigos]
    tabela.upsert({"chave": CHAVE_CONFIG_PDF, "valor": config}, on_conflict="chave").execute()
    salvo = tabela.select("valor").eq("chave", CHAVE_CONFIG_PDF).execute()
    if not salvo.data or salvo.data[0]["valor"] != config:
        raise RuntimeError("A configuração gravada não corresponde à atualização solicitada.")
    print(f"{len(CODIGOS_PADRAO_PDF)} grupos atualizados e verificados em {CHAVE_CONFIG_PDF}.")


if __name__ == "__main__":
    main()
