"""Provisão de 13º: totais por estabelecimento e saldos da planilha anterior."""

import io
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from decimal import Decimal

import fitz
import pandas as pd

COLUNAS = ['Filial', 'Diferença de saldo', 'Saldo anterior planilha',
           'Saldo anterior folha', 'D-269.1 - 13º salário',
           'D-1324.2 - Enc. s/13º sal.', 'Pagas',
           'D-162.7 Prov 13º sal - C-1324.2 Enc.', 'Total prov. 13º']
ROTULOS = ['Saldo Acumulado Anterior:', 'Pagamento no Mês:', 'Reversão no Mês:',
           'Total do Débito:', 'Provisão do Mês:', 'Saldo Acumulado Atual:']


def extrair_provisao_13(conteudo):
    registros, periodos = {}, set()
    with fitz.open(stream=conteudo, filetype='pdf') as doc:
        for pagina, page in enumerate(doc, 1):
            texto = page.get_text()
            periodos.update(re.findall(r'Provisões de 13[°º] Salário (\d{2}/\d{4})', texto))
            words = page.get_text('words')
            for marker in page.search_for('Total por Estabelecimento'):
                nome = page.get_textbox(fitz.Rect(0, marker.y0, marker.x1 + 100, marker.y1 + 15))
                match = re.search(r'(\d+)\s*-\s*Buffon\s+(\d+)', nome)
                if not match:
                    raise ValueError(f'Estabelecimento inválido na página {pagina}.')
                codigo, unidade = map(int, match.groups())
                filial = 'Matriz' if unidade == 1 else f'Filial {unidade-1}'
                if codigo != 1000 + unidade or unidade < 1 or filial in registros:
                    raise ValueError(f'Estabelecimento duplicado ou inválido: {codigo}.')
                anteriores = [r for r in page.search_for(ROTULOS[0]) if r.y0 < marker.y0]
                if not anteriores:
                    raise ValueError(f'Saldo anterior ausente na página {pagina}.')
                inicio = max(r.y0 for r in anteriores)
                linhas = {}
                for rotulo in ROTULOS:
                    candidatos = [r for r in page.search_for(rotulo) if inicio-1 <= r.y0 <= inicio+85]
                    if len(candidatos) != 1:
                        raise ValueError(f'{rotulo} ausente ou ambíguo na página {pagina}.')
                    rect = candidatos[0]
                    valores = [w[4] for w in sorted(words, key=lambda w: w[0])
                               if abs(w[1]-rect.y0) < 2 and w[0] > rect.x1
                               and re.fullmatch(r'-?[\d.]+,\d{2}|-', w[4])]
                    if len(valores) != 7:
                        raise ValueError(f'{rotulo} incompleto na página {pagina}.')
                    linhas[rotulo] = [Decimal(v.replace('.', '').replace(',', '.')) if v != '-' else Decimal(0) for v in valores]
                ant, pag, rev, deb, prov, atual = [linhas[r] for r in ROTULOS]
                valores = [ant[6], prov[0]-rev[0], prov[4]+prov[5], pag[0], deb[4]+deb[5]]
                total = valores[0]+valores[1]+valores[2]-valores[3]-valores[4]
                if total != atual[6]:
                    raise ValueError(f'Total calculado difere do PDF em {filial}, página {pagina}: {total} / {atual[6]}.')
                registros[filial] = {'valores': valores + [total], 'pagina': pagina, 'codigo': codigo,
                                     'origem': [prov[0], rev[0], prov[4], prov[5], deb[4], deb[5]]}
    if not registros or len(periodos) != 1:
        raise ValueError('Provisão sem totais por estabelecimento ou competência única.')
    return {'competencia': periodos.pop(), 'registros': registros}


def ler_saldos(conteudo, nome, competencia):
    if nome.lower().endswith('.ods'):
        ns = {'t': 'urn:oasis:names:tc:opendocument:xmlns:table:1.0', 'o': 'urn:oasis:names:tc:opendocument:xmlns:office:1.0'}
        with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
            root = ET.fromstring(z.read('content.xml'))
        abas = {}
        for aba in root.findall('.//t:table', ns):
            linhas = []
            for row in aba.findall('t:table-row', ns):
                cells = []
                for cell in row:
                    value = cell.get('{'+ns['o']+'}value')
                    value = Decimal(value) if value is not None else ''.join(cell.itertext()).strip()
                    cells.extend([value] * min(int(cell.get('{'+ns['t']+'}number-columns-repeated', '1')), 20-len(cells)))
                    if len(cells) >= 20:
                        break
                if any(str(c) for c in cells):
                    if int(row.get('{'+ns['t']+'}number-rows-repeated', '1')) != 1:
                        raise ValueError('Linhas preenchidas repetidas na planilha.')
                    linhas.append(cells)
            abas[aba.get('{'+ns['t']+'}name')] = linhas
    else:
        abas = {n: df.fillna('').values.tolist() for n, df in pd.read_excel(io.BytesIO(conteudo), sheet_name=None, header=None).items()}
    candidatas = [rows for name, rows in abas.items() if re.search(r'provis', name, re.I) and '13' in name]
    if len(candidatas) != 1:
        raise ValueError('É necessária uma única aba Provisão 13º na planilha.')
    rows = candidatas[0]
    titulo = ' '.join(str(c) for row in rows[:5] for c in row)
    periodo = re.search(r'(\d{2})/(\d{4})', titulo)
    if not periodo:
        raise ValueError('Competência ausente no título da planilha de provisão.')
    periodo = '/'.join(periodo.groups())
    anterior = (datetime.strptime(competencia, '%m/%Y') - timedelta(days=1)).strftime('%m/%Y')
    if periodo == competencia and 'sl ant em folha' in titulo.lower():
        coluna = 2  # Modelo já iniciado por Bruna: C contém o fechamento anterior.
    elif periodo == anterior:
        headers = next((r for r in rows if r and str(r[0]).strip().lower() == 'filial'), [])
        indices = [i for i, c in enumerate(headers) if 'total prov' in str(c).lower()]
        if len(indices) != 1:
            raise ValueError('Coluna Total prov. 13º não encontrada na planilha anterior.')
        coluna = indices[0]
    else:
        raise ValueError('Use a planilha do mês anterior ou o modelo do mês atual com os saldos anteriores.')
    saldos = {}
    for row in rows:
        label = str(row[0]).strip() if row else ''
        m = re.fullmatch(r'(?:Filial\s*|F)0*(\d+)', label, re.I)
        if label.lower() not in ('matriz', 'mtz') and not m:
            continue
        filial = f'Filial {int(m[1])}' if m else 'Matriz'
        if filial in saldos:
            raise ValueError(f'Filial duplicada na planilha: {filial}.')
        v = row[coluna] if len(row) > coluna else ''
        if v == '':
            saldos[filial] = None
            continue
        if isinstance(v, str):
            v = v.replace('.', '').replace(',', '.')
        saldo = Decimal(str(v))
        if not saldo.is_finite():
            raise ValueError(f'Saldo anterior inválido: {filial}.')
        saldos[filial] = saldo
    return saldos


def apurar_provisao_13(pdf, planilha, nome):
    dados = extrair_provisao_13(pdf)
    saldos = ler_saldos(planilha, nome, dados['competencia'])
    faltantes = {f for f in dados['registros'] if saldos.get(f) is None}
    dados['avisos'] = []
    if faltantes:
        dados['avisos'].append('Saldo anterior e diferença considerados zero por ausência na planilha: ' + ', '.join(sorted(faltantes)))
    extras = set(saldos) - set(dados['registros'])
    if extras:
        dados['avisos'].append('Filiais da planilha sem total no PDF: ' + ', '.join(sorted(extras)))
    for filial, r in dados['registros'].items():
        r['saldo_ausente'] = filial in faltantes
        r['saldo_planilha'] = saldos.get(filial) if filial not in faltantes else Decimal(0)
    return dados


def tabela_provisao_13(dados):
    rows = []
    for filial in sorted(dados['registros'], key=lambda f: 0 if f == 'Matriz' else int(f.split()[-1])):
        r = dados['registros'][filial]
        saldo = r['saldo_planilha']
        nome = 'Mtz' if filial == 'Matriz' else f'F{int(filial.split()[-1]):02d}'
        rows.append([nome, 0.0 if r['saldo_ausente'] else float(saldo-r['valores'][0]),
                     float(saldo), *map(float, r['valores'])])
    return pd.DataFrame(rows, columns=COLUNAS)


def escrever_provisao_13(writer, dados):
    tabela = tabela_provisao_13(dados)
    nome = 'Provisão 13º'
    tabela.to_excel(writer, sheet_name=nome, startrow=5, index=False, header=False)
    ws, wb = writer.sheets[nome], writer.book
    num = wb.add_format({'num_format': '#,##0.00', 'align': 'right', 'valign': 'vcenter'})
    header = wb.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', 'border': 1})
    titulo = wb.add_format({'bold': True, 'font_size': 14, 'align': 'left', 'valign': 'vcenter'})
    subtitulo = wb.add_format({'bold': True, 'font_size': 12, 'align': 'left', 'valign': 'vcenter'})
    total = wb.add_format({'bold': True, 'num_format': '#,##0.00', 'align': 'right', 'valign': 'vcenter'})
    ws.merge_range('A1:I1', 'COMERCIAL BUFFON COMB. E TRANSPORTES LTDA', titulo)
    ws.merge_range('A2:I2', 'Com Buffon / Provisão 13º - '+dados['competencia'], subtitulo)
    for coluna in (0, 2, 3, 6, 8):
        ws.merge_range(3, coluna, 4, coluna, COLUNAS[coluna], header)
    for coluna, debito, credito in (
        (1, 'D-162.7 Prov 13º sal', 'C-269.1 13º sal - Dif. saldo'),
        (4, 'D-269.1 - 13º salário', 'C-162.7 Prov 13º sal'),
        (5, 'D-1324.2 - Enc. s/13º sal.', 'C-162.7 Prov 13º sal'),
        (7, 'D-162.7 Prov 13º sal', 'C-1324.2 - Enc. s/13º sal.'),
    ):
        ws.write(3, coluna, debito, header)
        ws.write(4, coluna, credito, header)
    ws.set_column('B:I', None, num)
    ws.freeze_panes(5, 0)
    for i, row in enumerate(tabela.itertuples(index=False, name=None), 5):
        n = i+1
        filial = 'Matriz' if row[0] == 'Mtz' else f'Filial {int(row[0][1:])}'
        registro = dados['registros'][filial]
        valores = [f'({v:f})' if v < 0 else format(v, 'f') for v in registro['origem']]
        ws.write_formula(i, 4, f'={valores[0]}-{valores[1]}', num, row[4])
        ws.write_formula(i, 5, f'={valores[2]}+{valores[3]}', num, row[5])
        ws.write_formula(i, 7, f'={valores[4]}+{valores[5]}', num, row[7])
        ws.write_formula(i, 1, f'=IF(C{n}=0,0,C{n}-D{n})' if registro['saldo_ausente'] else f'=C{n}-D{n}', num, row[1])
        ws.write_formula(i, 8, f'=D{n}+E{n}+F{n}-G{n}-H{n}', num, row[8])
    fim = 5+len(tabela)
    ws.write(fim, 0, 'TOTAL GERAL', total)
    for c in range(1, 9):
        letra = chr(65+c)
        formula = f'SUM({letra}6:{letra}{fim})'
        ws.write_formula(fim, c, '='+formula, total, float(tabela.iloc[:, c].sum()))
    nota = wb.add_format({'text_wrap': True, 'valign': 'top'})
    for i, aviso in enumerate(dados['avisos']):
        linha = fim+2+i*2
        ws.merge_range(linha, 0, linha+1, 8, aviso, nota)
    ws.autofit()
    return ws
