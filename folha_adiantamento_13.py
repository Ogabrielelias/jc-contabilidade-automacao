"""Leitura e exportação do adiantamento de 13º por estabelecimento."""

import re
from decimal import Decimal

import fitz
import pandas as pd

from folha_pdf import detectar_filial


def extrair_adiantamento_13(conteudo):
    """Retorna None para outros relatórios; rejeita adiantamentos incompletos."""
    with fitz.open(stream=conteudo, filetype="pdf") as documento:
        texto = "\n".join(pagina.get_text() for pagina in documento)
    if not re.search(r"00030001\s*-", texto):
        return None
    periodo = re.search(
        r"Folhas de \d{2}/\d{2}/\d{4} a \d{2}/(\d{2}/\d{4})", texto
    )
    if not periodo:
        raise ValueError("Competência não encontrada no PDF de adiantamento.")
    registros = {}
    # O total da empresa pode estar na mesma página da última filial.
    # No texto extraído, o rodapé de totais encerra os valores da unidade.
    for bloco in re.split(r"(?m)(?=^Estabelecimento:)", texto)[1:]:
        filial = detectar_filial(bloco)
        if filial is None:
            continue
        bloco = bloco.split("Totais do Estabelecimento:")[0]
        registro = registros.setdefault(filial, {})
        for coluna, rotulo in (
            ("Ad 13 Sal.", r"(?:Vl\.\s*L[ií]quido|L[ií]quido)"),
            ("Fgts s/ 13 sal.", r"Vlr\.?\s*FGTS"),
        ):
            valor = re.search(rotulo + r":\s*(-?[\d.]+,\d{2})", bloco, re.I)
            if valor:
                numero = Decimal(valor[1].replace(".", "").replace(",", "."))
                if coluna in registro and registro[coluna] != numero:
                    raise ValueError(f"Totais conflitantes para {filial}.")
                registro[coluna] = numero
    if not registros or any(len(r) != 2 for r in registros.values()):
        raise ValueError("Líquido ou Vlr. FGTS ausente no resumo de uma filial.")
    return {"competencia": periodo[1], "registros": registros}


def tabela_adiantamento_13(dados, filiais=()):
    unidades = set(dados["registros"]) | set(filiais) | {"Matriz", "Filial 1", "Filial 2"}
    unidades = sorted(
        unidades, key=lambda f: 0 if f == "Matriz" else int(f.split()[-1])
    )
    tabela = pd.DataFrame([
        {
            "Filial": "Mtz" if filial == "Matriz" else f"F{int(filial.split()[-1]):02d}",
            **{
                coluna: float(dados["registros"][filial][coluna])
                if filial in dados["registros"] else None
                for coluna in ("Ad 13 Sal.", "Fgts s/ 13 sal.")
            },
        }
        for filial in unidades
    ])
    colunas_valores = ["Ad 13 Sal.", "Fgts s/ 13 sal."]
    tabela = tabela.loc[
        tabela[colunas_valores].fillna(0).ne(0).any(axis=1)
    ].reset_index(drop=True)
    tabela.loc[len(tabela)] = {
        "Filial": "TOTAL GERAL",
        **tabela[colunas_valores].sum().round(2).to_dict(),
    }
    return tabela


def escrever_adiantamento_13(writer, dados, filiais=()):
    tabela = tabela_adiantamento_13(dados, filiais)
    nome = "Ad 13 Sal e FGTS"
    tabela.to_excel(writer, sheet_name=nome, index=False, startrow=3)
    workbook = writer.book
    worksheet = writer.sheets[nome]
    titulo = workbook.add_format({
        "bold": True, "font_size": 14, "align": "left", "valign": "vcenter",
    })
    subtitulo = workbook.add_format({
        "bold": True, "font_size": 12, "align": "left", "valign": "vcenter",
    })
    moeda = workbook.add_format({
        "num_format": "#,##0.00", "align": "right", "valign": "vcenter",
    })
    worksheet.merge_range(
        "A1:G1", "COMERCIAL BUFFON COMB. E TRANSPORTES LTDA", titulo
    )
    worksheet.merge_range(
        "A2:G2", f"Com Buffon / Ad 13 sal / FGTS - {dados['competencia']}", subtitulo
    )
    worksheet.set_column("B:C", None, moeda)
    total = workbook.add_format({
        "bold": True, "align": "right", "valign": "vcenter",
        "num_format": "#,##0.00",
    })
    worksheet.set_row(len(tabela) + 3, None, total)
    worksheet.autofit()
    return worksheet
