"""Fórmulas dos relatórios, com entradas rastreáveis e resultados em cache."""

import re
from decimal import Decimal
from xlsxwriter.utility import xl_rowcol_to_cell as cell


def valor_excel(valor):
    if isinstance(valor, str):
        return float(valor.replace('R$', '').replace('.', '').replace(',', '.').strip())
    return float(valor)


def filial_excel(nome):
    m = re.fullmatch(r'Buffon\s+(\d+)', str(nome), re.I)
    return ('Matriz' if int(m[1]) == 1 else f'Filial {int(m[1])-1}') if m else str(nome)


def formulas_folha(writer, lancamentos, resumo, prolabore, fgts, selecionados,
                   especiais, codigos_prolabore, codigos_inss, inicio_prolabore):
    wb = writer.book
    moeda = wb.add_format({'num_format': '#,##0.00', 'align': 'right'})
    total = wb.add_format({'num_format': '#,##0.00', 'align': 'right', 'bold': True})
    inteiro = wb.add_format({'num_format': '0', 'align': 'right'})
    total_inteiro = wb.add_format({'num_format': '0', 'align': 'right', 'bold': True})
    valores_por_filial = {}
    for r in lancamentos.itertuples(index=False):
        valores_por_filial.setdefault(filial_excel(r.filial), []).append(
            (str(r.codigo), str(r.digito), Decimal(str(r.valor_num)))
        )

    def soma(filial, codigos=None, tipo=None):
        codigos = None if codigos is None else {str(c) for c in codigos}
        termos = []
        for codigo, digito, valor in valores_por_filial.get(filial_excel(filial), []):
            if (codigos is None or codigo in codigos) and (tipo is None or digito == tipo):
                texto = format(valor, 'f')
                termos.append(f'({texto})' if valor < 0 else texto)
        return '+'.join(termos) or '0'

    ws = writer.sheets['Resumo Salários']
    cols = {c: i for i, c in enumerate(resumo.columns)}
    salario = 'D-266.6 - T. salário'
    subtotal = 'C-152.0 -  Sub. T.'
    pagar = 'C-152.0 - Sal. a pagar'
    caixa = 'C-22667 - D-CAIXA (Desc. emp. Consig.)'
    for i, (_, row) in enumerate(resumo.iterrows(), 5):
        filial = row['Filial']
        is_total = filial in ('T. GERAL', 'TOTAL GERAL')
        ref = lambda c: cell(i, cols[c])
        for c, j in cols.items():
            if c.strip() == 'Filial':
                continue
            formula = None
            if is_total:
                formula = f'SUM({cell(5,j)}:{cell(i-1,j)})' if i > 5 else '0'
            elif c == 'Total proventos':
                formula = soma(filial, tipo='P')
            elif c == 'Total proventos e descontos selecionados':
                formula = soma(filial, selecionados)
            elif c == salario:
                formula = f'ROUND({soma(filial, tipo="P")}-({soma(filial, selecionados)}),2)'
            elif c in especiais:
                formula = f'ROUND({soma(filial, especiais[c])},2)'
            elif c == subtotal:
                formula = ref(salario)+'-('+ '+'.join(ref(k) for k in list(especiais)[:11])+')'
            elif c == pagar:
                formula = '+'.join(ref(k) for k in (subtotal, 'D-54.0 - Sal. Fam.', 'D-53.1 - Sal. Mat.'))
            elif c == 'Resultado':
                formula = ref(pagar)+'-'+ref(caixa)
            if formula:
                formato = (total_inteiro if c == 'Func.' else total) if is_total else (inteiro if c == 'Func.' else moeda)
                ws.write_formula(i, j, '='+formula, formato, valor_excel(row[c]))
            else:
                ws.write_number(i, j, valor_excel(row[c]), inteiro if c == 'Func.' else moeda)

    if 'Resumo Salários e Funcionários' in writer.sheets:
        ws_func = writer.sheets['Resumo Salários e Funcionários']
        for i, (_, row) in enumerate(resumo.iterrows(), 3):
            origem = i+2
            for j, nome in ((1, 'Func.'), (2, salario)):
                is_total = row['Filial'] in ('T. GERAL', 'TOTAL GERAL')
                formato = (total_inteiro if j == 1 else total) if is_total else (inteiro if j == 1 else moeda)
                ws_func.write_formula(i, j, f"='Resumo Salários'!{cell(origem, cols[nome])}",
                                      formato, valor_excel(row[nome]))

    for i, (_, row) in enumerate(prolabore.iterrows(), inicio_prolabore):
        filial = row['Filial']
        is_total = row['Filial'] in ('T. GERAL', 'TOTAL GERAL')
        formulas = [f'ROUND({soma(filial, codigos_prolabore)},2)',
                    f'ROUND({soma(filial, codigos_inss)},2)', f'{cell(i,3)}-{cell(i,4)}']
        for j, nome in enumerate(('Prolabore', 'INSS', 'Total Líquido'), 3):
            formula = (f'SUM({cell(inicio_prolabore,j)}:{cell(i-1,j)})' if i > inicio_prolabore else '0') if is_total else formulas[j-3]
            ws.write_formula(i, j, '='+formula, total if is_total else moeda, valor_excel(row[nome]))

    if not fgts.empty and 'FGTS e Honorários' in writer.sheets:
        ws_fgts = writer.sheets['FGTS e Honorários']
        referencias = []
        for i, (_, row) in enumerate(fgts.iterrows()):
            r, c = 4+i%50, (i//50)*3+1
            if row.iloc[0] in ('T. GERAL', 'TOTAL GERAL'):
                ws_fgts.write_formula(r, c, '=SUM('+','.join(referencias)+')' if referencias else '=0', total, valor_excel(row.iloc[1]))
            else:
                ws_fgts.write_number(r, c, valor_excel(row.iloc[1]), moeda)
                referencias.append(cell(r, c))
