# JC Contabilidade - Documentacao do projeto

## 1. Objetivo

O projeto e uma aplicacao web em Streamlit para apoiar o fechamento mensal da folha de salarios dos Postos Buffon. A fonte principal pode ser o novo PDF da folha, sem CSV, ou o CSV do padrao antigo. Ela extrai os lancamentos, agrupa os valores por filial, calcula resumos de salarios, pro-labore, FGTS e provisao de 13o salario, e permite baixar os resultados em arquivos Excel.

O processamento e feito em memoria durante a sessao do Streamlit. A configuracao dos grupos de codigos contabeis e persistida no Supabase.

## 2. Arquivos e responsabilidades

| Arquivo | Responsabilidade |
| --- | --- |
| `app.py` | Interface, leitura dos arquivos, parsing, calculos, tabelas e exportacao Excel. |
| `folha_pdf.py` | Extracao dos resumos PDF nos formatos antigo e novo, com continuacao de paginas e exclusao de totais gerais. |
| `folha_detalhes_ui.py` | Carregamento em cache dos dados do novo PDF. A consulta detalhada nao e exibida na pagina. |
| `folha_config.py` | Esquema dos grupos de eventos e conversao dos eventos PDF em lancamentos. |
| `folha_config_ui.py` | Formulario de configuracao do novo PDF, com salvamento explicito. |
| `scripts/inicializar_config_pdf.py` | Cria a chave inicial do novo PDF se ausente, preservando registros existentes. |
| `tests/test_folha_pdf.py` | Testes de regressao dos parsers e dos dois PDFs de exemplo, quando disponiveis. |
| `pages/ajuda.py` | Pagina de ajuda acessivel como pagina Streamlit; atualmente contem apenas os expanderes, sem conteudo explicativo. |
| `requirements.txt` | Dependencias Python: Streamlit, pandas, XlsxWriter, OpenPyXL, PyMuPDF, Supabase e httpx. |
| `Dockerfile` | Imagem Python 3.11 e comando de inicializacao do Streamlit na porta 8080. |
| `fly.toml` | Configuracao de deploy no Fly.io, regiao primaria `gru`, 1 GB de memoria e 1 CPU compartilhada. |

## 3. Entrada de dados

### Fluxo sem CSV (novo PDF)

1. Selecione `Novo PDF da folha` e envie o PDF no campo de funcionarios.
2. Na aba `Resumo Salarios`, abra `Configuracao de codigos somados por coluna`, associe os eventos e clique em `Salvar configuracao e calcular`. Os grupos seguem o padrao antigo: duas colunas com secoes expansiveis por categoria.
3. O mesmo PDF fornece vencimentos, descontos, funcionarios (apenas contratos ativos) e FGTS. Bases e totais da empresa nao sao somados novamente como lancamentos.
4. A competencia da exportacao vem do periodo impresso no PDF. Nome e CNPJ individuais ficam vazios porque o relatorio e agregado por estabelecimento.
5. O PDF de provisao de 13o continua separado para saldos anteriores, ajustes, transferencias e pagamentos.

O seletor `CSV (padrao antigo)` preserva o fluxo anterior e seus grupos de codigos.

### 3.1 CSV da folha

O CSV e lido com autodeteccao do delimitador. Linhas e colunas completamente vazias sao removidas. A aplicacao espera, no minimo, a estrutura de colunas que permite identificar:

- contabilidade;
- codigo;
- descricao;
- valor;
- nome do empregado ou favorecido;
- divisor;
- filial;
- CNPJ;
- digito do lancamento.

Quando necessario, colunas vazias sao adicionadas ate atingir 15 colunas. Os nomes internos sao padronizados e as colunas a partir da oitava sao concatenadas em `Informacoes_Complementares`. Essa informacao e interpretada por expressao regular para separar descricao, valor, nome, divisor, filial, CNPJ e digito.

Somente registros com `contabilidade` igual a `1` ou `6` permanecem. Registros com digito `N` sao removidos.

Antes dos calculos, o processamento antigo aplica uma lista fixa de exclusao:
`3101`, `4000`, `4006`, `4013`, `4017`, `4019`, `4025` e `20069`.
Essa lista nao possui campo de configuracao na interface do CSV e nao e carregada
do banco. A regra em `app.py` funciona assim:

1. Verifica se existe uma coluna chamada exatamente `1.4` em `df_final`.
2. Compara os valores dessa coluna com os codigos da lista fixa.
3. Remove somente as linhas correspondentes cujo `digito` seja `P` (provento).

As linhas removidas deixam de participar de todos os calculos e da aba
`Dados Extraidos`. Descontos (`D`) nao sao removidos por essa regra.
Se a coluna `1.4` nao existir, essa exclusao nao e aplicada; ela nao consulta
automaticamente a coluna `codigo` como alternativa.

O valor brasileiro e convertido para `valor_num`, usando ponto como separador decimal. Para exibicao, volta ao formato `R$ 1.234,56`.

### 3.2 PDF de funcionarios

Cada pagina e lida com PyMuPDF. A aplicacao identifica:

- filial ou matriz pelo texto `RESUMO Filial: N` ou `RESUMO Matriz: N`;
- quantidade de funcionarios pelo padrao `Nesta Folha N`.

No novo formato (2026), a filial vem de `Estabelecimento: 1002 - Buffon 02`.
`Buffon 01` corresponde a Matriz e `Buffon N` a Filial N-1. A quantidade de
funcionarios considera apenas `Contratos Ativos`; afastados e rescindidos nao
entram na coluna `Func.`. A consulta detalhada preserva todos os campos do PDF.
Cabecalhos repetidos em paginas de continuacao nao duplicam filiais. Os totais
da empresa e o resumo geral do formato antigo nao entram como uma filial.

O resultado e uma tabela com `Filial` e `Func.`. Essa tabela e associada ao resumo de salarios pela filial.

Os dados detalhados do PDF continuam sendo extraidos para os calculos.
O container de consulta `Dados completos do novo PDF da folha` foi removido da pagina.

### 3.3 PDF de quebra/FGTS

O PDF e lido pagina a pagina para identificar a filial pelo mesmo resumo e o salario pelo texto `Mensal + 13o Salario valor`. O salario extraido e usado no resumo de FGTS e na base da provisao mensal de 13o.

No novo formato, o valor de FGTS e extraido do campo `Vlr. FGTS`, sem confundir
com `Base FGTS`. O novo PDF da folha pode ser enviado tambem no campo de FGTS.

### 3.4 PDF de proventos de 13o

O relatorio e percorrido por linhas de texto. A aplicacao detecta `Total Filial: N`, cria uma tabela para cada filial e extrai as colunas:

`Descricao`, `Total Anterior`, `Total Mes`, `Transferencias`, `Total Pagas`, `Ajuste` e `Total`.

Valores no padrao brasileiro, inclusive valores entre parenteses, sao convertidos para numero. Linhas sem descricao sao renomeadas sequencialmente para `Subtotal Provisao`, `Subtotal Encargos` e `Subtotal FGTS`.

## 4. Padronizacao de filiais

As funcoes `mapear_filial`, `detectar_filial`, `detectar_provento_filial`, `sort_buffon` e `sort_filial` mantem uma nomenclatura comum:

- `Matriz` permanece `Matriz`;
- `Buffon N` vira `Filial N-1`;
- no PDF de proventos, `Total Filial: 1` vira `Matriz` e os demais viram `Filial N-1`;
- a ordenacao coloca Matriz primeiro, depois as filiais numericas.

Essa conversao e importante porque os arquivos podem usar numeracoes diferentes para a mesma unidade.

## 5. Configuracao dos codigos contabeis

As funcoes `salvar_config` e `carregar_config` acessam a tabela Supabase `configuracoes_codigos`, usando `chave` e `valor`. Se o banco estiver indisponivel, a aplicacao exibe aviso e usa os valores padrao definidos em `app.py`.

Existem dois grupos de configuracao:

No fluxo antigo (CSV):

1. `codigos_padrao`: codigos selecionados para formar o total de salario liquido `D-266.6 - T. salario`.
2. `COLUNAS_ESPECIAIS`: grupos de codigos somados por filial para formar as colunas de descontos, beneficios, encargos e demais categorias do resumo.

O usuario pode alterar os grupos na tela. A alteracao e salva no Supabase e afeta os calculos da sessao e das sessoes seguintes.

Para o novo PDF, todos os grupos ficam em uma linha independente da mesma tabela,
com `chave = folha_pdf_v1` e `valor` contendo:

- `versao` e `configurado`;
- `excluir_proventos`: vencimentos retirados dos lancamentos de todos os calculos;
- `codigos_padrao`: eventos deduzidos do total de vencimentos para formar T. salario;
- `colunas_especiais`: listas de eventos das 14 colunas contabeis, em ordem fixa;
- `prolabore` e `inss_prolabore`: eventos utilizados no resumo de pro-labore.

Os codigos do PDF sao strings de oito digitos. O formulario mostra codigo, descricao
e tipo; permite digitar codigos de meses futuros e remover codigos ausentes no PDF
atual. Os grupos contabeis possuem os padroes informados pelo usuario em
`CODIGOS_PADRAO_PDF` (`folha_config.py`). Adiantamento de 13o, exclusoes,
deducoes para T. salario continuam sem padroes presumidos.
Pro-labore usa por padrao `00001501` e seu INSS usa `00063401`, ambos editaveis.
Listas salvas explicitamente vazias sao respeitadas, sem repor codigos removidos.
O calculo inicia apos salvar a primeira configuracao. Falhas de gravacao sao exibidas
e nao substituem a configuracao anterior.
A configuracao do novo PDF nao altera `codigos_padrao` nem `COLUNAS_ESPECIAIS` do CSV.

### 5.1 Vencimentos excluidos e deducoes do salario

No novo PDF, a secao `Codigos de vencimentos excluidos` controla a lista
`excluir_proventos`. Ela inicia vazia e pode ser editada e salva pelo usuario.
Nao ha conversao automatica da lista fixa de codigos do CSV antigo.

A exclusao ocorre durante a conversao dos eventos PDF em lancamentos, antes dos
calculos. Um evento selecionado e removido apenas se seu tipo for `Vencimento`.
Seu valor deixa de entrar no resumo de salarios, nos grupos contabeis e no
pro-labore, e sua linha nao aparece na aba `Dados Extraidos`. Os descontos nao
sao removidos por essa lista. A exclusao nao altera o PDF nem os totais de FGTS
e contratos lidos diretamente do documento.

Ja os `Codigos para calculo da D-266.6 - T. Salario` (`codigos_padrao`) deduzem
os eventos selecionados do total de vencimentos para formar T. salario. Esses
eventos continuam disponiveis nos lancamentos e podem compor outros grupos.

Por exemplo, colocar `00001501` em `excluir_proventos` retira o vencimento de
pro-labore tambem do resumo de pro-labore. Coloca-lo apenas em `codigos_padrao`
deduz seu valor na formacao de T. salario, mantendo-o disponivel para o grupo
de pro-labore. Este exemplo descreve o efeito dos campos, sem alterar suas listas.

## 6. Calculos do resumo de salarios

### 6.1 Totais por filial

O total de proventos e a soma de `valor_num` de todos os registros cujo digito e `P`, agrupados por filial:

```text
Total proventos = soma(valor_num dos lancamentos P)
```

O total dos codigos escolhidos para salario e calculado da mesma forma:

```text
Total codigos selecionados = soma(valor_num dos codigos configurados)
```

O campo exibido como `D-266.6 - T. salario` e:

```text
D-266.6 - T. salario = Total proventos - Total codigos selecionados
```

Cada coluna especial e a soma, por filial, dos codigos associados a ela. Quando nao ha lancamento para uma filial, o valor e preenchido com zero.

### 6.2 Subtotal e salario a pagar

As primeiras 11 colunas especiais, na ordem configurada, entram no subtotal:

```text
C-152.0 - Sub. T. = D-266.6 - T. salario
                    - soma(primeiras 11 colunas especiais)
```

Salario-familia e salario-maternidade sao adicionados ao subtotal para formar o salario a pagar:

```text
C-152.0 - Sal. a pagar = C-152.0 - Sub. T.
                         + D-54.0 - Sal. Fam.
                         + D-53.1 - Sal. Mat.
```

O resultado final desconta a coluna de D-CAIXA:

```text
Resultado = C-152.0 - Sal. a pagar
           - C-22667 - D-CAIXA (Desc. emp. Consig.)
```

Os nomes e os codigos das colunas sao definidos pelo dicionario `COLUNAS_ESPECIAIS`; portanto, a ordem desse dicionario interfere na formula acima.

### 6.3 Totais gerais

Depois dos calculos por filial, as colunas monetarias sao convertidas temporariamente para numero, somadas e uma linha `T. GERAL` e adicionada. A quantidade de funcionarios, quando veio do PDF, tambem e somada.

## 7. Calculo de pro-labore

No CSV antigo, o resumo de pro-labore usa diretamente os codigos:

- codigo `17`: valor de pro-labore;
- codigo `940`: INSS.

Por filial:

```text
Pro-labore = soma(valor_num onde codigo = 17)
INSS = soma(valor_num onde codigo = 940)
Total liquido = Pro-labore - INSS
```

Uma linha `T. GERAL` soma as tres colunas.

## 8. Calculo de FGTS e provisao mensal de 13o

Quando o PDF de quebra/FGTS esta disponivel, o salario `D-266.6 - T. salario` do resumo principal e associado a cada filial. A partir dele sao calculados:

```text
Provisao mensal de 13o = D-266.6 - T. salario / 12
Encargos sobre 13o = Provisao mensal de 13o * 0,258
Total provisao 13o = Provisao mensal de 13o + Encargos sobre 13o
```

O salario extraido do PDF aparece como `D-271.2 FGTS - C-145.7 FGTS a rec`. Os totais gerais sao obtidos pela soma das linhas de cada coluna.

## 9. Consolidacao do PDF de provisao de 13o

Para cada filial, `consolidar_provisoes` extrai:

- saldo anterior;
- provisao de 13o do mes;
- encargos sobre 13o;
- valores pagos;
- valores pagos/relacionados ao FGTS;
- total informado no relatorio.

A provisao mensal incorpora ajuste e transferencia:

```text
Provisao considerada = Total Mes + Ajuste + Transferencias
Encargos considerados = Total Mes + Ajuste + Transferencias da linha FGTS
```

Depois, a aplicacao recalcula o total:

```text
Total prov. 13o = Saldo anterior
                 + Provisao de 13o
                 + Encargos sobre 13o
                 - Pagas
                 - Prov. 13o paga/FGTS pago
```

Uma diferenca temporaria entre o total calculado e o total informado e compensada: quando os encargos sao zero, a diferenca e ajustada nos encargos; caso contrario, e ajustada no valor pago de provisao. Em seguida o total e recalculado e a linha `TOTAL GERAL` e adicionada.

## 10. Fluxo operacional

1. A aplicacao inicia o Streamlit e cria o cliente Supabase usando `st.secrets["supabase_url"]` e `st.secrets["supabase_key"]`.
2. O usuario envia o CSV e os PDFs desejados.
3. Os nomes dos arquivos sao analisados para extrair mes e ano no padrao `MM AAAA`; divergencias entre os arquivos geram um alerta.
4. O CSV e interpretado, filtrado, normalizado e convertido em `df_final`.
5. Os PDFs sao interpretados independentemente e seus dados sao associados por filial.
6. A interface mostra as abas `Resumo Salarios`, `Resumo FGTS`, `Resumo prolabore`, `Provisao 13o salario` e `Dados Extraidos`.
7. O usuario pode filtrar os dados extraidos por filial, tipo e codigo.
8. Os resultados podem ser exportados em um ou mais arquivos `.xlsx`.

## 11. Exportacao Excel

O arquivo principal e gerado com `pandas.ExcelWriter` e `xlsxwriter`. Dependendo dos arquivos enviados, pode conter:

- `Resumo Salarios`: resumo por filial, codigos contabeis, totais, salario a pagar e resultado;
- `Resumo Salarios e Funcionarios`: salario e quantidade de funcionarios, alem de uma area de resumo por empresa;
- `FGTS e Honorarios`: dados do FGTS e area reservada para honorarios;
- `Provisao 13o`: consolidacao da provisao de 13o.

Os cabecalhos podem ser escritos em duas linhas, separando codigo e descricao. A funcao `escrever_dataframe_em_blocos` divide tabelas grandes em blocos de ate 50 linhas para montar a planilha. Os nomes dos arquivos incluem mes e ano quando essa informacao foi identificada.

## 12. Funcoes principais

### Persistencia e configuracao

- `has_supabase_error(resp)`: identifica erro retornado pelo Supabase.
- `salvar_config(chave, valor)`: faz upsert da configuracao.
- `carregar_config(chave, default)`: carrega uma configuracao ou retorna o padrao.

### Filiais e ordenacao

- `mapear_filial(valor)`: padroniza nomes de filiais.
- `detectar_filial(texto)`: extrai filial/matriz de uma pagina de PDF.
- `detectar_provento_filial(texto)`: extrai filial de linhas de provisao.
- `sort_buffon`, `sort_filial` e `sort_tipo`: definem a ordem de exibicao.

### Extracao e conversao

- `extrair_tabelas_por_filial(uploaded_file)`: extrai tabelas de provisao do PDF.
- `detectar_funcionarios(texto)`: extrai quantidade de funcionarios.
- `detectar_salario(texto)`: extrai salario mensal mais 13o.
- `br_to_float(valor)` e `limpar_e_converter(valor)`: convertem valores brasileiros.
- `separar_header_em_duas_linhas(header_list)`: separa codigo e descricao para Excel.
- `format_df_prov_13(df)`: formata valores da provisao em reais.
- `corrigir_subtotais(df)`: identifica e nomeia subtotais sem descricao.
- `consolidar_provisoes(tabelas_filiais)`: consolida a provisao por filial.

### Exportacao

- `trocar_headers_d_com_c(header_df, header_codigos)`: ajusta pares de cabecalho de debito/credito.
- `escrever_dataframe_em_blocos(...)`: escreve dataframes em blocos, com formatos e cabecalhos personalizados.

## 13. Dependencias e execucao

Execucao local:

```bash
pip install -r requirements.txt
streamlit run app.py
```

A aplicacao requer os secrets `supabase_url` e `supabase_key` no ambiente Streamlit. Em container, o `Dockerfile` inicia o servico na porta 8080:

```bash
streamlit run app.py --server.port=8080 --server.address=0.0.0.0
```

## 14. Limitacoes e cuidados do comportamento atual

- Os parsers dependem dos textos e formatos dos relatorios originais. Mudancas no layout dos PDFs ou do CSV podem impedir a extracao.
- Mes e ano sao inferidos principalmente pelo nome dos arquivos, nao pelo conteudo dos relatorios.
- A associacao entre fontes depende da nomenclatura padronizada das filiais e pode produzir linhas com zero quando uma filial existe em apenas um arquivo.
- O percentual de encargos da provisao de 13o esta fixo em `25,8%` no codigo.
- Os calculos de salario a pagar usam posicoes das colunas especiais, alem dos nomes; alterar a ordem dos grupos pode alterar a formula.
- A pagina `pages/ajuda.py` existe, mas seus expanderes ainda estao vazios.
- Os testes de extracao podem ser executados com `python -m unittest discover -s tests -v`. Os testes dos PDFs reais sao ignorados quando os exemplos nao estao presentes. A validacao do fluxo completo de calculo e exportacao tambem requer o CSV da competencia.
- O cliente Supabase e criado na inicializacao. Sem os secrets necessarios, a aplicacao nao inicia corretamente.
