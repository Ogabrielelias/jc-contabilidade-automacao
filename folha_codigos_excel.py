"""Rastreabilidade dos eventos utilizados na exportação de salários."""


def escrever_codigos_calculos(workbook, lancamentos, selecionados, especiais,
                             prolabore, inss_prolabore, mes_ano,
                             formato_titulo, formato_subtitulo, formato_cabecalho):
    aba = workbook.add_worksheet("Códigos dos Cálculos")
    texto = workbook.add_format({"valign": "top"})
    descricoes = {}
    for codigo, descricao in lancamentos[["codigo", "descricao"]].itertuples(index=False, name=None):
        descricoes.setdefault(str(codigo), str(descricao))
    grupos = [
        ("D-266.6 - T. salário", selecionados),
        *especiais.items(),
        ("Pró-labore — Prolabore", prolabore),
        ("Pró-labore — INSS", inss_prolabore),
    ]
    for indice, (coluna, codigos) in enumerate(grupos):
        codigo_contabil, separador, nome = coluna.partition(" - ")
        aba.write_string(2, indice, codigo_contabil if separador else "", formato_cabecalho)
        aba.write_string(3, indice, nome if separador else coluna, formato_cabecalho)
        for numero, codigo in enumerate(dict.fromkeys(str(c) for c in codigos), start=4):
            descricao = descricoes.get(codigo, "Não encontrado na origem")
            valor = f"{codigo} - {descricao}"
            # Texto explícito preserva zeros à esquerda e evita fórmulas acidentais.
            aba.write_string(numero, indice, valor, texto)
    # Ajustar pelos cabeçalhos e eventos, sem incluir os títulos mesclados.
    aba.autofit()
    aba.merge_range("A1:G1", "COMERCIAL BUFFON COMB. E TRANSPORTES LTDA",
                    formato_titulo)
    aba.merge_range("A2:G2", f"CÓDIGOS DOS CÁLCULOS REFERENTES MÊS {mes_ano}",
                    formato_subtitulo)
    aba.set_row(0, 22)
    aba.set_row(1, 20)
    aba.set_row(2, 20)
    aba.set_row(3, 20)
    aba.freeze_panes(4, 0)
