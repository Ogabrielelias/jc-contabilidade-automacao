"""Leitura dos resumos de folha antigos e por estabelecimento (2026)."""

import re

import fitz


def detectar_filial(texto):
    antigo = re.search(r"RESUMO\s+(Filial|Matriz):\s*(\d+)", texto, re.I)
    if antigo:
        if antigo[1].lower() == "matriz":
            return "Matriz"
        return f"Filial {int(antigo[2]) - 1}"

    novo = re.search(
        r"Estabelecimento:\s*\d+\s*-\s*Buffon\s+(\d+)\b", texto, re.I
    )
    if novo:
        numero = int(novo[1])
        return "Matriz" if numero == 1 else f"Filial {numero - 1}"
    return None


def detectar_funcionarios(texto, incluir_afastados=False):
    antigo = re.search(r"Nesta\s+Folha\s*:?\s*(\d+)", texto, re.I)
    if antigo:
        return int(antigo[1])
    ativos = re.search(r"Contratos\s+Ativos:\s*(\d+)", texto, re.I)
    if ativos:
        afastados = re.search(r"Contratos\s+Afastados:\s*(\d+)", texto, re.I)
        return int(ativos[1]) + (
            int(afastados[1]) if incluir_afastados and afastados else 0
        )
    return None


def detectar_salario(texto):
    """Valor do FGTS; mantém o nome usado pelo processamento existente."""
    for padrao in (
        r"Mensal\s*\+\s*13º\s*Salário\s+([\d.]+,\d{2})",
        r"Vlr\.\s*FGTS:\s*([\d.]+,\d{2})",
    ):
        match = re.search(padrao, texto, re.I)
        if match:
            return match[1]
    return None


def extrair_resumos_paginas(textos, incluir_afastados=False):
    """Uma linha por filial, inclusive quando seus totais estão na próxima página."""
    resultados = {}
    filial_atual = None
    for texto in textos:
        if re.search(r"RESUMO\s+DO\s+PERÍODO|Totais\s+da\s+Empresa:", texto, re.I):
            filial_atual = None
            continue

        filial = detectar_filial(texto)
        if filial is not None:
            filial_atual = filial
            resultados.setdefault(filial, {"Filial": filial, "Func.": None})

        if filial_atual is None:
            continue

        registro = resultados[filial_atual]
        funcionarios = detectar_funcionarios(texto, incluir_afastados)
        fgts = detectar_salario(texto)
        if funcionarios is not None and registro["Func."] is None:
            registro["Func."] = funcionarios
        if fgts is not None and "Salário" not in registro:
            registro["Salário"] = fgts

    return list(resultados.values())


def extrair_resumos_pdf(conteudo, incluir_afastados=False):
    with fitz.open(stream=conteudo, filetype="pdf") as doc:
        return extrair_resumos_paginas(
            (pagina.get_text() for pagina in doc), incluir_afastados
        )


def extrair_detalhes_pdf(conteudo):
    """Extrai os campos impressos da nova folha, mantendo a página de origem."""
    dados = {"documento": [], "resumos": [], "eventos": [], "categorias": []}
    numero = r"-?\d[\d.]*,\d{2}"
    resumos = {}
    with fitz.open(stream=conteudo, filetype="pdf") as doc:
        textos = [pagina.get_text() for pagina in doc]
    if not any(re.search(r"Estabelecimento:\s*\d+\s*-\s*Buffon", t) for t in textos):
        return dados

    primeiro = textos[0]
    periodo = re.search(r"Folhas de (\d{2}/\d{2}/\d{4}) a (\d{2}/\d{2}/\d{4})", primeiro)
    emissao = re.search(r"\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}", primeiro)
    empresa = re.search(r"Totais da Empresa:\s*([^\n]+)", "\n".join(textos))
    dados["documento"] = [{
        "Empresa": empresa[1] if empresa else primeiro.splitlines()[0],
        "Relatório": "Folha de Pagamento",
        "Início": periodo[1] if periodo else None,
        "Fim": periodo[2] if periodo else None,
        "Emissão": emissao[0] if emissao else None,
        "Páginas": len(textos),
    }]
    for pagina, texto in enumerate(textos, 1):
        estabelecimento = re.search(r"Estabelecimento:\s*(\d+)\s*-\s*(Buffon\s+\d+)", texto)
        # No novo layout, todas as páginas de filial repetem o estabelecimento.
        # As páginas sem esse cabeçalho são o consolidado da empresa.
        unidade = detectar_filial(texto) if estabelecimento else "Total da empresa"
        contexto = {
            "Unidade": unidade,
            "Estabelecimento": estabelecimento[1] if estabelecimento else "",
            "Nome": estabelecimento[2] if estabelecimento else "Total da empresa",
        }
        resumo = resumos.setdefault(unidade, {**contexto, "Páginas": []})
        resumo["Páginas"].append(pagina)
        for campo in ("Base INSS", "Base IRRF", "Base FGTS", "Vlr. FGTS", "Total Venc.", "Total Desc.", "Líquido"):
            match = re.search(re.escape(campo) + r":\s*(" + numero + ")", texto)
            if match:
                resumo[campo] = match[1]
        for campo in ("Contratos Ativos", "Contratos Afastados", "Contratos Rescindidos"):
            match = re.search(re.escape(campo) + r":\s*(\d+)", texto)
            if match:
                resumo[campo] = int(match[1])

        tipo = None
        linhas = texto.splitlines()
        for i, linha in enumerate(linhas):
            linha = linha.strip()
            if linha in ("Vencimento", "Desconto", "Base"):
                tipo = linha
            evento = re.fullmatch(r"(\d{8})\s*-\s*(.+)", linha)
            if evento:
                valores = linhas[i + 1:i + 3]
                if tipo is None or len(valores) != 2 or not all(re.fullmatch(numero, v.strip()) for v in valores):
                    raise ValueError(f"Evento {evento[1]} incompleto na página {pagina}.")
                dados["eventos"].append({
                    **contexto, "Tipo": tipo, "Código": evento[1],
                    "Descrição": evento[2], "Horas/QTD": valores[0].strip(),
                    "Valor": valores[1].strip(), "Página": pagina,
                })
            categoria = re.fullmatch(r"((?:Empregado|Contribuinte individual)\s*[–-].+):\s*(\d+)", linha)
            if categoria:
                dados["categorias"].append({
                    **contexto, "Categoria": categoria[1],
                    "Contratos": int(categoria[2]), "Página": pagina,
                })
    for resumo in resumos.values():
        resumo["Páginas"] = ", ".join(map(str, resumo["Páginas"]))
        if "Contratos Ativos" in resumo and "Contratos Afastados" in resumo:
            resumo["Ativos + afastados"] = resumo["Contratos Ativos"] + resumo["Contratos Afastados"]
        dados["resumos"].append(resumo)
    return dados
