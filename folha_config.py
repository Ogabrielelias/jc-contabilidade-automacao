"""Configuração independente do plano de eventos da nova folha PDF."""

import pandas as pd

CHAVE_CONFIG_PDF = "folha_pdf_v1"
COLUNAS_PDF = [
    "C-270.4 - INSS", "C-147.3 - IRF rec.", "C-275.5 - V.T.",
    "C-297.6 - Farm.", "C-51.5 - Ad. Sal.", "C-51.5 - Desc. Ad. Sal.",
    "C-2267.5 - Conf. dívida", "C-142.2 - P.Alim.", "C-297.6 - Pl. Saúde",
    "C-146.5 - Sind. Rec.", "C-302.6 - Cest. Bas.", "D-54.0 - Sal. Fam.",
    "D-53.1 - Sal. Mat.",
    "C-22667 - D-CAIXA (Desc. emp. Consig.)",
]

# Padrões informados pelo usuário. As escolhas salvas continuam editáveis.
CODIGOS_PADRAO_PDF = {
    "C-270.4 - INSS": [63101],
    "C-147.3 - IRF rec.": [64101],
    "C-275.5 - V.T.": [56001],
    "C-297.6 - Farm.": [60001],
    "C-51.5 - Ad. Sal.": [
        60002, 60003, 60004, 60005, 60006, 60007, 60008, 60009, 60010,
        60022, 60023, 60024, 60025, 60026, 60027, 60028, 60029, 60030,
    ],
    "C-51.5 - Desc. Ad. Sal.": [52001, 52101],
    "C-2267.5 - Conf. dívida": [56121],
    "C-142.2 - P.Alim.": [54101],
    "C-297.6 - Pl. Saúde": [58001, 58002, 58101, 58102, 58103, 58104, 58113, 58201, 58202],
    "C-146.5 - Sind. Rec.": [53401],
    "C-302.6 - Cest. Bas.": [57014, 60011],
    "D-54.0 - Sal. Fam.": [41101],
    "D-53.1 - Sal. Mat.": [40, 43, 44, 45, 46, 48],
    "C-22667 - D-CAIXA (Desc. emp. Consig.)": [
        61501, 61502, 61503, 61504, 61505, 61506, 61507, 61508, 61509,
    ],
}


def config_pdf_inicial():
    return {
        "versao": 1, "configurado": False,
        "codigos_padrao": [],
        "prolabore": ["00001501"], "inss_prolabore": ["00063401"],
        "colunas_especiais": {
            coluna: [str(codigo).zfill(8) for codigo in CODIGOS_PADRAO_PDF.get(coluna, [])]
            for coluna in COLUNAS_PDF
        },
    }


def normalizar_config_pdf(config):
    resultado = config_pdf_inicial()
    if not isinstance(config, dict):
        return resultado
    resultado["configurado"] = config.get("configurado") is True

    def codigos(valores):
        if not isinstance(valores, list):
            raise ValueError("A configuração deve conter listas de códigos.")
        saida = []
        for valor in valores:
            codigo = str(valor).strip()
            if not codigo.isdigit() or len(codigo) > 8:
                raise ValueError(f"Código de evento inválido: {codigo}")
            saida.append(codigo.zfill(8))
        return sorted(set(saida))

    for chave in ("codigos_padrao", "prolabore", "inss_prolabore"):
        resultado[chave] = codigos(config.get(chave, resultado[chave]))
    for coluna in COLUNAS_PDF:
        resultado["colunas_especiais"][coluna] = codigos(
            config.get("colunas_especiais", {}).get(coluna, resultado["colunas_especiais"][coluna])
        )
    return resultado


def dataframe_lancamentos_pdf(dados, config):
    """Adapta apenas eventos das unidades ao contrato usado nos cálculos atuais."""
    linhas = []
    for evento in dados["eventos"]:
        if evento["Unidade"] == "Total da empresa" or evento["Tipo"] == "Base":
            continue
        valor = float(evento["Valor"].replace(".", "").replace(",", "."))
        linhas.append({
            "codigo": evento["Código"], "descricao": evento["Descrição"],
            "valor": f"R${evento['Valor']}", "valor_num": valor,
            "nome": "", "cnpj": "", "filial": evento["Unidade"],
            "digito": "P" if evento["Tipo"] == "Vencimento" else "D",
        })
    return pd.DataFrame(linhas, columns=[
        "codigo", "descricao", "valor", "valor_num", "nome", "cnpj", "filial", "digito"
    ])
