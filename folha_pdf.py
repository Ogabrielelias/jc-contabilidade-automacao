"""Leitura dos resumos de folha antigos e por estabelecimento (2026)."""

import re
from decimal import Decimal

import fitz


def detectar_filial(texto):
    antigo = re.search(r"RESUMO\s+(Filial|Matriz):\s*(\d+)", texto, re.I)
    if antigo:
        if antigo[1].lower() == "matriz":
            return "Matriz"
        return f"Filial {int(antigo[2]) - 1}"

    novo = re.search(
        r"(?:Estabelecimento:\s*)?\d+\s*[-–—]?\s*Buffon\s+(\d+)\b", texto, re.I
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


def _eventos_layout_lado_a_lado(palavras, contexto, pagina, texto):
    """Extrai eventos do layout com vencimentos e descontos em colunas paralelas."""
    if not re.search(r"Folha\s+De\s+Pagamento\s*-\s*Estabelecimentos", texto, re.I):
        return None
    por_linha = []
    for palavra in sorted(palavras, key=lambda w: w[1]):
        if not por_linha or palavra[1] - por_linha[-1][0] > 1.0:
            por_linha.append([palavra[1], [palavra]])
        else:
            por_linha[-1][1].append(palavra)

    cabecalho_vencimentos = next((w[0] for w in palavras if w[4].lower() == "vencimentos"), None)
    cabecalho_descontos = next((w[0] for w in palavras if w[4].lower() == "descontos"), None)
    if cabecalho_vencimentos is None or cabecalho_descontos is None:
        return None
    if contexto["Unidade"] == "Total da empresa":
        # O consolidado da empresa usa um relatório próprio e seus valores já
        # aparecem nos totais; não o misture com os eventos das filiais.
        return []
    if not any(re.fullmatch(r"\d{8}", w[4]) and w[0] >= 280 for w in palavras):
        return None
    cabecalhos_base = [
        y for y, linha in por_linha
        if sum(w[4].upper() == "BASE" for w in linha) >= 2
        and sum(w[4].upper() == "VALOR" for w in linha) >= 2
    ]
    inicio_bases = min(cabecalhos_base) if cabecalhos_base else float("inf")
    numero = re.compile(r"\(?-?\d[\d.]*,\d{2}\)?")
    eventos = []

    for y, palavras_linha in por_linha:
        codigos = [w for w in palavras_linha if re.fullmatch(r"\d{8}", w[4])]
        for codigo in codigos:
            esquerdo = codigo[0] < 300
            faixa_valores = (lambda w: 180 < w[0] < 300) if esquerdo else (lambda w: w[0] >= 450)
            valores = [w for w in palavras_linha if faixa_valores(w) and numero.fullmatch(w[4])]
            if len(valores) != 2:
                raise ValueError(f"Evento {codigo[4]} incompleto na p?gina {pagina}.")
            primeiro_valor_x = min(w[0] for w in valores)
            descricao = " ".join(
                w[4] for w in sorted(palavras_linha, key=lambda w: w[0])
                if codigo[2] < w[0] < primeiro_valor_x
            )
            descricao = descricao.removeprefix("-").strip()
            tipo = "Base" if y >= inicio_bases else ("Vencimento" if esquerdo else "Desconto")
            normalizados = [w[4].strip("()") for w in sorted(valores, key=lambda w: w[0])]
            eventos.append({
                **contexto, "Tipo": tipo, "Código": codigo[4],
                "Descrição": descricao, "Horas/QTD": normalizados[0],
                "Valor": normalizados[1], "Página": pagina,
            })
    return eventos

def extrair_detalhes_pdf(conteudo):
    """Extrai os campos impressos da nova folha, mantendo a página de origem."""
    dados = {"documento": [], "resumos": [], "eventos": [], "categorias": []}
    numero = r"-?\d[\d.]*,\d{2}"
    resumos = {}
    with fitz.open(stream=conteudo, filetype="pdf") as doc:
        paginas = [(pagina.get_text(), pagina.get_text("words")) for pagina in doc]
    textos = [texto for texto, _ in paginas]
    if not any(re.search(
        r"(?:Estabelecimento:\s*)?\d+\s*[-–—]?\s*Buffon\s+\d+", t, re.I
    ) for t in textos):
        return dados

    primeiro = textos[0]
    periodo = re.search(r"Folhas de (\d{2}/\d{2}/\d{4}) a (\d{2}/\d{2}/\d{4})", primeiro)
    emissao = re.search(r"\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}", primeiro)
    empresa = re.search(
        r"(?:Totais da Empresa:\s*|Total Da Empresa:\s*\d+\s*-\s*)([^\n]+)",
        "\n".join(textos), re.I,
    )
    dados["documento"] = [{
        "Empresa": empresa[1] if empresa else primeiro.splitlines()[0],
        "Relatório": "Folha de Pagamento",
        "Início": periodo[1] if periodo else None,
        "Fim": periodo[2] if periodo else None,
        "Emissão": emissao[0] if emissao else None,
        "Páginas": len(textos),
    }]
    for pagina, (texto, palavras) in enumerate(paginas, 1):
        estabelecimento = re.search(
            r"(?:Estabelecimento:\s*)?(\d+)\s*[-–—]?\s*(Buffon\s+\d+)", texto, re.I
        )
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
        linhas_texto = texto.splitlines()
        campos_resumo = ("Base INSS", "Base IRRF", "Base FGTS", "Vlr. FGTS", "Total Venc.", "Total Desc.", "Líquido")
        for campo in campos_resumo:
            for i, linha in enumerate(linhas_texto):
                match = re.fullmatch(re.escape(campo) + r":\s*(.*)", linha.strip())
                if not match:
                    continue
                valor = match[1].strip()
                rotulo_anterior = i > 0 and any(
                    re.fullmatch(re.escape(outro) + r":\s*", linhas_texto[i - 1].strip())
                    for outro in campos_resumo
                )
                if not valor and i + 1 < len(linhas_texto) and not rotulo_anterior:
                    valor = linhas_texto[i + 1].strip()
                if re.fullmatch(numero, valor):
                    resumo[campo] = valor
                break
        for campo in ("Contratos Ativos", "Contratos Afastados", "Contratos Rescindidos"):
            match = re.search(re.escape(campo) + r":\s*(\d+)", texto)
            if match:
                resumo[campo] = int(match[1])

        eventos_colunas = _eventos_layout_lado_a_lado(palavras, contexto, pagina, texto)
        if eventos_colunas is not None:
            dados["eventos"].extend(eventos_colunas)

        tipo = None
        linhas = texto.splitlines()
        for i, linha in enumerate(linhas):
            linha = linha.strip()
            if re.fullmatch(r"(?:Vencimento|Provento)s?", linha, re.I):
                tipo = "Vencimento"
            elif re.fullmatch(r"Descontos?", linha, re.I):
                tipo = "Desconto"
            elif re.fullmatch(r"Bases?", linha, re.I):
                tipo = "Base"
            evento = re.fullmatch(r"(\d{8})\s*-\s*(.+)", linha) if eventos_colunas is None else None
            if evento:
                valores = []
                for seguinte in linhas[i + 1:]:
                    seguinte = seguinte.strip()
                    if re.fullmatch(r"(?:Vencimento|Provento|Desconto|Base)s?", seguinte, re.I) or re.fullmatch(r"\d{8}\s*-\s*.+", seguinte):
                        break
                    valores.extend(re.findall(numero, seguinte))
                    if len(valores) >= 2:
                        break
                if tipo is None or len(valores) != 2:
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
    eventos_unicos = {}
    for evento in dados["eventos"]:
        chave = (
            evento["Unidade"], evento["Tipo"],
            evento[next(k for k in evento if k.startswith("C"))],
            evento["Horas/QTD"], evento["Valor"],
        )
        eventos_unicos.setdefault(chave, evento)
    dados["eventos"] = list(eventos_unicos.values())

    codigos_base = {
        "Base INSS": ("00077101", "00077201"),
        "Base IRRF": ("00078101", "00078201"),
        "Base FGTS": ("00079101", "00079201"),
        "Vlr. FGTS": ("00079501", "00079511"),
        "Total Venc.": ("00099100",),
        "Total Desc.": ("00099200",),
        "L\u00edquido": ("00099991",),
    }
    codigos_por_unidade = {}
    for evento in dados["eventos"]:
        if evento["Tipo"] != "Base":
            continue
        chave_codigo = next(chave for chave in evento if chave.startswith("C"))
        codigo = evento[chave_codigo]
        unidade = evento["Unidade"]
        codigos_por_unidade.setdefault(unidade, {}).setdefault(codigo, []).append(
            Decimal(evento["Valor"].replace(".", "").replace(",", "."))
        )

    for resumo in resumos.values():
        unidade = resumo["Unidade"]
        codigos = codigos_por_unidade.get(unidade, {})
        for campo, codigos_referencia in codigos_base.items():
            if campo in resumo:
                continue
            valores = [valor for codigo in codigos_referencia for valor in codigos.get(codigo, [])]
            if valores:
                total = sum(valores, Decimal(0))
                resumo[campo] = f"{total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        resumo["Páginas"] = ", ".join(map(str, resumo["Páginas"]))
        if "Contratos Ativos" in resumo and "Contratos Afastados" in resumo:
            resumo["Ativos + afastados"] = resumo["Contratos Ativos"] + resumo["Contratos Afastados"]
        dados["resumos"].append(resumo)
    return dados
