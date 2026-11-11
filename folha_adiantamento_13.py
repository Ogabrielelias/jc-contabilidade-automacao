"""Leitura e exportação do adiantamento de 13º por estabelecimento."""

import re
from decimal import Decimal

import fitz
import pandas as pd

from folha_pdf import detectar_filial

HEADERS_ADIANTAMENTO = {
    "Ad 13 Sal.": ("D-52.3 ad 13 sal", "C-2478.3 13 a pg"),
    "Fgts s/ 13 sal.": ("D-271.2 FGTS", "C-145.7 FGTS a pg"),
}


def _valor_evento_adiantamento(texto, codigo):
    numero = r"\(?-?\d[\d.]*,\d{2}\)?"
    linhas = texto.splitlines()
    for i, linha in enumerate(linhas):
        if not re.match(rf"\s*{codigo}\s*-", linha):
            continue
        valores = []
        for seguinte in linhas[i + 1:]:
            seguinte = seguinte.strip()
            if re.match(r"\d{8}\s*-", seguinte):
                break
            valores.extend(re.findall(numero, seguinte))
            if len(valores) >= 2:
                break
        if len(valores) == 2:
            return Decimal(valores[-1].strip("()").replace(".", "").replace(",", "."))
        raise ValueError(f"Evento {codigo} incompleto no PDF de adiantamento.")
    return None


def _extrair_adiantamento_layout_atual(paginas):
    periodo = re.search(
        r"Folhas de \d{2}/\d{2}/\d{4} a \d{2}/(\d{2}/\d{4})", "\n".join(paginas)
    )
    if not periodo:
        raise ValueError("Competência não encontrada no PDF de adiantamento.")

    registros = {}
    for texto in paginas:
        filial = detectar_filial(texto)
        if filial is None or not re.search(r"00030001\s*-", texto):
            continue
        liquido = _valor_evento_adiantamento(texto, "00099995")
        fgts = _valor_evento_adiantamento(texto, "00079521")
        if liquido is None or fgts is None:
            raise ValueError(f"Líquido ou FGTS ausente no resumo de {filial}.")
        registro = {"Ad 13 Sal.": liquido, "Fgts s/ 13 sal.": fgts}
        if filial in registros and registros[filial] != registro:
            raise ValueError(f"Totais conflitantes para {filial}.")
        registros[filial] = registro
    if not registros:
        raise ValueError("Nenhum estabelecimento encontrado no PDF de adiantamento.")
    return {"competencia": periodo[1], "registros": registros}


def extrair_adiantamento_13(conteudo):
    """Retorna None para outros relatórios; rejeita adiantamentos incompletos."""
    with fitz.open(stream=conteudo, filetype="pdf") as documento:
        paginas = [pagina.get_text() for pagina in documento]
        texto = "\n".join(paginas)
    if not re.search(r"00030001\s*-", texto):
        return None
    if re.search(r"Folha\s+De\s+Pagamento\s*-\s*Estabelecimentos", texto, re.I):
        return _extrair_adiantamento_layout_atual(paginas)
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
    return tabela.rename(columns={
        coluna: " - ".join(headers)
        for coluna, headers in HEADERS_ADIANTAMENTO.items()
    })


def escrever_adiantamento_13(writer, dados, filiais=()):
    tabela = tabela_adiantamento_13(dados, filiais)
    nome = "Ad 13 Sal e FGTS"
    tabela.to_excel(writer, sheet_name=nome, index=False, header=False, startrow=5)
    workbook = writer.book
    worksheet = writer.sheets[nome]
    cabecalho = workbook.add_format({
        "bold": True, "align": "center", "valign": "vcenter", "border": 1, "text_wrap": True,
    })
    worksheet.merge_range("A4:A5", "Filial", cabecalho)
    for coluna, headers in enumerate(HEADERS_ADIANTAMENTO.values(), 1):
        worksheet.write(3, coluna, headers[0], cabecalho)
        worksheet.write(4, coluna, headers[1] + f"\nH-{172 + coluna}", cabecalho)
    worksheet.set_row(4, 32)
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
    worksheet.set_row(len(tabela) + 4, None, total)
    for coluna, letra in enumerate('BC', 1):
        formula = f'=SUM({letra}6:{letra}{len(tabela)+4})' if len(tabela) > 1 else '=0'
        worksheet.write_formula(len(tabela)+4, coluna, formula, total, float(tabela.iloc[-1, coluna]))
    worksheet.autofit()
    return worksheet
