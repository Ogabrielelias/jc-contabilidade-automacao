import streamlit as st
import pandas as pd
import io
import csv
import re
from datetime import datetime, timedelta


def mapear_filial(valor):
    valor = str(valor).strip()

    if valor.lower() == "matriz":
        return "Matriz"

    m = re.match(r"Buffon\s+(\d+)", valor, re.IGNORECASE)
    if m:
        numero = int(m.group(1))
        return f"Filial {numero - 1}"

    return valor


def sort_buffon(value):
    value = str(value).strip()

    if value.lower() == "matriz":
        return (0, 0)

    m = re.match(r"Buffon\s+(\d+)", value)
    if m:
        return (1, int(m.group(1)))

    return (2, value)


def sort_filial(value):
    value = str(value).strip()

    if value.lower() == "matriz":
        return (0, 0)

    m = re.match(r"Filial\s+(\d+)", value)
    if m:
        return (1, int(m.group(1)))

    return (2, value)


def sort_tipo(value):
    order = {
        "Provento": 0,
        "Desconto": 1,
    }
    return order.get(value, 99)


st.set_page_config(page_title="JC Contabilidade - Postos Buffon", layout="wide")

st.markdown(
    """
    <style>
    .stMainBlockContainer {
      padding-top: 2.5rem;
    }
    h1, h2, h3, h4, h5, h6 {
      padding: 0 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("JC Contabilidade")

st.markdown("<hr style='padding:0;margin:16px 0;'>", unsafe_allow_html=True)

with st.container(border=True):
    st.header("Postos Buffon - Folha de Salários")
    st.write(
        "Envie aqui o arquivo **CSV original** recebido por e-mail."
        "O sistema faz a leitura automática do formato e extrai as informações contábeis."
    )
    uploaded_file = st.file_uploader("Selecione o arquivo CSV", type=["csv"])

    if uploaded_file is not None:
        try:
            uploaded_file.seek(0)
            uploaded_file = io.BytesIO(uploaded_file.read())
            content = uploaded_file.getvalue().decode("utf-8", errors="ignore")
            sniffer = csv.Sniffer()
            delimiter = sniffer.sniff(content.splitlines()[0]).delimiter

            df = pd.read_csv(
                io.StringIO(content),
                delimiter=delimiter,
                engine="python",
                on_bad_lines="skip",
                header=None,
            )

            df = df.dropna(axis=1, how="all")
            df = df.dropna(axis=0, how="all")

            min_cols = 15
            num_cols = df.shape[1]

            if num_cols < min_cols:
                for i in range(num_cols + 1, min_cols + 1):
                    df[f"col_{i}"] = None

            df.columns = [
                "col_1",
                "col_2",
                "col_3",
                "contabilidade",
                "col_5",
                "col_6",
                "col_7",
                "codigo",
                "descricao",
                "valor",
                "nome",
                "divisor",
                "filial",
                "cnpj",
                "digito",
            ] + list(df.columns[15:])

            if "contabilidade" in df.columns:
                df = df[
                    (df["contabilidade"].astype(str).str.strip() == "1")
                    | (df["contabilidade"].astype(str).str.strip() == "6")
                ]
                df = df[df["digito"] != "N"]

            if df.shape[1] > 9:
                primeiras_colunas = df.iloc[:, :8]
                colunas_para_juntar = df.iloc[:, 8:]

                df["Informações_Complementares"] = colunas_para_juntar.astype(
                    str
                ).apply(
                    lambda x: " ".join(
                        [
                            v.strip().replace("(", "").replace(")", "")
                            for v in x
                            if str(v).strip() not in ["", "nan", "None"]
                        ]
                    ),
                    axis=1,
                )
                df = pd.concat(
                    [primeiras_colunas, df["Informações_Complementares"]], axis=1
                )
            else:
                st.warning(
                    "O arquivo possui menos de 8 colunas. Nenhuma junção foi feita."
                )

            def extrair_info(texto):
                texto = str(texto)
                padrao = re.compile(
                    r"^(?P<descricao>.*?)\s+(?P<valor>\d+(?:[.,]\d{1,2}))\s+(?P<nome>.+?)\s+(?P<divisor>-\d*)\s+(?P<filial>.+?)\s+(?P<cnpj>\d{14})\s+(?P<digito>[PDN])$"
                )
                match = padrao.search(texto.strip())
                if match:
                    return match.groupdict()
                else:
                    return {
                        "descricao": None,
                        "valor": None,
                        "nome": None,
                        "divisor": None,
                        "filial": None,
                        "cnpj": None,
                        "digito": None,
                    }

            extraidos = (
                df["Informações_Complementares"].apply(extrair_info).apply(pd.Series)
            )
            df_final = pd.concat(
                [df.drop(columns=["Informações_Complementares"]), extraidos], axis=1
            )

            df_final["valor_num"] = pd.to_numeric(
                df_final["valor"].astype(str).str.replace(",", "."), errors="coerce"
            )

            df_final["valor"] = df_final["valor_num"].apply(
                lambda x: (
                    f"R${x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                    if pd.notnull(x)
                    else x
                )
            )

            df_final = df_final.drop(df_final.columns[:7], axis=1)
            df_final = df_final[df_final["digito"] != "N"]

            codigos_excluir = [
                "3101",
                "4000",
                "4006",
                "4013",
                "4017",
                "4019",
                "4025",
                "20069",
            ]

            if "1.4" in df_final.columns:
                df_final = df_final[
                    ~(
                        (df_final["digito"] == "P")
                        & (df_final["1.4"].astype(str).isin(codigos_excluir))
                    )
                ]

        except Exception as e:
            st.error(
                "O arquivo enviado não corresponde ao padrão esperado. "
                "Certifique-se de utilizar o CSV original recebido por e-mail ou contate o suporte."
            )
            print(f"[ERRO] {e}")
            st.stop()

if uploaded_file is not None and "df_final" in locals():
    with st.container(border=True):
        st.header("Resultados da extração")

        try:

            tabs = st.tabs(["Resumo Salários", "Dados Extraídos"])

            with tabs[1]:
                st.write(
                    "Tabela com todos os lançamentos extraídos do arquivo. "
                    "Você pode filtrar por **filial** e **tipo (Provento, Desconto)**."
                )
                df_table = df_final[
                    ["codigo", "descricao", "valor", "nome", "filial", "cnpj", "digito"]
                ]
                digito_map = {
                    "P": "Provento",
                    "D": "Desconto",
                }

                df_table["digito"] = df_table["digito"].apply(
                    lambda x: digito_map.get(x, x)
                )

                df_table["filial"] = df_table["filial"].apply(mapear_filial)

                df_table = df_table.sort_values(
                    by=["filial", "digito"],
                    key=lambda col: (
                        col.map(sort_filial)
                        if col.name == "filial"
                        else col.map(sort_tipo)
                    ),
                )

                df_table["codigo_fmt"] = (
                    df_table["codigo"].astype(str)
                    + " – "
                    + df_table["descricao"].astype(str)
                )

                codigo_map = dict(
                    zip(df_table["codigo_fmt"], df_table["codigo"].astype(str))
                )

                col1, col2, col3 = st.columns(3)

                with col1:
                    filiais_opcoes = sorted(
                        df_table["filial"].dropna().unique(), key=sort_filial
                    )
                    filiais_selecionadas = st.multiselect(
                        "Filtrar por Filial:",
                        filiais_opcoes,
                        default=None,
                        placeholder="Selecione uma ou mais filiais",
                    )

                with col2:
                    tipos_opcoes = sorted(
                        df_table["digito"].dropna().unique(), key=sort_tipo
                    )
                    tipos_selecionados = st.multiselect(
                        "Filtrar por Tipo:",
                        tipos_opcoes,
                        default=None,
                        placeholder="Selecione um ou mais tipos",
                    )

                with col3:
                    codigos_opcoes = sorted(
                        df_table["codigo_fmt"].dropna().unique(),
                        key=lambda x: int(x.split(" – ")[0]),
                    )
                    codigos_selecionados_fmt = st.multiselect(
                        "Filtrar por Código:",
                        codigos_opcoes,
                        default=None,
                        placeholder="Selecione um ou mais códigos",
                    )

                    codigos_selecionados = [
                        codigo_map[x] for x in codigos_selecionados_fmt
                    ]

                df_filtrado = df_table.copy()

                if len(filiais_selecionadas) > 0:
                    df_filtrado = df_filtrado[
                        df_filtrado["filial"].isin(filiais_selecionadas)
                    ]

                if len(tipos_selecionados) > 0:
                    df_filtrado = df_filtrado[
                        df_filtrado["digito"].isin(tipos_selecionados)
                    ]
                if len(codigos_selecionados) > 0:
                    df_filtrado = df_filtrado[
                        df_filtrado["codigo"].astype(str).isin(codigos_selecionados)
                    ]

                df_filtrado = df_filtrado.rename(
                    columns={
                        "codigo": "Código",
                        "descricao": "Descrição",
                        "valor": "Valor",
                        "nome": "Nome",
                        "filial": "Filial",
                        "cnpj": "CNPJ",
                        "digito": "Tipo",
                    }
                )

                df_filtrado = df_filtrado[
                    ["Filial", "Código", "Descrição", "Valor", "Tipo", "Nome", "CNPJ"]
                ]

                df_filtrado.reset_index(drop=True, inplace=True)

                st.dataframe(df_filtrado, use_container_width=True)

            # ===============================
            # PROVENTOS POR FILIAL
            # ===============================
            with tabs[0]:
                st.subheader("Resumo de Salários")
                st.write("")
                df_soma = (
                    df_final[df_final["digito"] == "P"]
                    .groupby("filial", as_index=False)["valor_num"]
                    .sum()
                )

                df_soma.rename(columns={"filial": "Nome da Filial"}, inplace=True)

                df_soma["Filial"] = df_soma["Nome da Filial"].apply(mapear_filial)

                # 🔧 CORREÇÃO AQUI — manter somente colunas existentes
                df_soma = df_soma[["Filial", "Nome da Filial", "valor_num"]]

                df_soma["total_proventos"] = df_soma["valor_num"].apply(
                    lambda x: f"R${x:,.2f}".replace(",", "X")
                    .replace(".", ",")
                    .replace("X", ".")
                )

                todos_codigos = sorted(
                    df_final["codigo"].astype(str).dropna().unique(),
                    key=lambda x: int(x),
                )

                codigos_P_padrao = ["17", "130", "169", "170", "171", "173", "907"]
                codigos_D_padrao = ["3", "6", "19", "22", "23", "24", "911", "938"]

                codigos_P_existentes = (
                    df_final[df_final["digito"] == "P"]["codigo"]
                    .astype(str)
                    .unique()
                    .tolist()
                )
                codigos_D_existentes = (
                    df_final[df_final["digito"] == "D"]["codigo"]
                    .astype(str)
                    .unique()
                    .tolist()
                )

                # Criar código – descrição apenas dentro do tipo correto
                df_final["codigo_desc"] = (
                    df_final["codigo"].astype(str)
                    + " – "
                    + df_final["descricao"].astype(str)
                )

                codigo_map = dict(
                    zip(df_final["codigo_desc"], df_final["codigo"].astype(str))
                )

                codigos_P_formatados = sorted(
                    [c for c in codigo_map if codigo_map[c] in codigos_P_existentes],
                    key=lambda x: int(x.split(" – ")[0]),
                )

                codigos_D_formatados = sorted(
                    [c for c in codigo_map if codigo_map[c] in codigos_D_existentes],
                    key=lambda x: int(x.split(" – ")[0]),
                )

                # Filtrar padrões que realmente existem no CSV
                codigos_P_default_fmt = [
                    c for c in codigos_P_formatados if codigo_map[c] in codigos_P_padrao
                ]
                codigos_D_default_fmt = [
                    c for c in codigos_D_formatados if codigo_map[c] in codigos_D_padrao
                ]

                with st.expander(
                    "Códigos que serão descontados do total de proventos para calcular o “D-266.6 - Total Salário”"
                ):
                    st.write(
                        "Os códigos listados abaixo permitem ajustar o cálculo do **total salário** "
                        "subtraindo valores específicos de proventos ou descontos. \n\n"
                        f"Os códigos padrão utilizados são: **{', '.join(codigos_P_padrao)} de proventos** e **{', '.join(codigos_D_padrao)} de descontos**. "
                        "Se algum deles não aparecer na lista, significa que **nenhuma filial utilizou esse código** "
                        "no arquivo enviado. Ainda assim, você pode selecionar livremente qualquer código disponível "
                        "para realizar o ajuste conforme necessário."
                    )
                    colP, colD = st.columns(2)

                with colP:
                    codigos_P_select_fmt = st.multiselect(
                        "Códigos de proventos:",
                        options=codigos_P_formatados,
                        default=codigos_P_default_fmt,
                    )
                    codigos_P_selecionados = [
                        codigo_map[x] for x in codigos_P_select_fmt
                    ]

                with colD:
                    codigos_D_select_fmt = st.multiselect(
                        "Códigos de descontos:",
                        options=codigos_D_formatados,
                        default=codigos_D_default_fmt,
                    )
                    codigos_D_selecionados = [
                        codigo_map[x] for x in codigos_D_select_fmt
                    ]

                df_codigos_especiais = (
                    df_final[
                        (
                            (df_final["digito"] == "P")
                            & (
                                df_final["codigo"]
                                .astype(str)
                                .isin(codigos_P_selecionados)
                            )
                        )
                        | (
                            (df_final["digito"] == "D")
                            & (
                                df_final["codigo"]
                                .astype(str)
                                .isin(codigos_D_selecionados)
                            )
                        )
                    ]
                    .groupby("filial", as_index=False)["valor_num"]
                    .sum()
                )

                df_codigos_especiais.rename(
                    columns={"valor_num": "total_codigos_especiais"}, inplace=True
                )

                df_soma = df_soma.merge(
                    df_codigos_especiais,
                    left_on="Nome da Filial",
                    right_on="filial",
                    how="left",
                ).drop(columns=["filial"])

                df_soma["total_codigos_especiais"] = df_soma[
                    "total_codigos_especiais"
                ].fillna(0)

                df_soma["total_codigos_especiais_fmt"] = df_soma[
                    "total_codigos_especiais"
                ].apply(
                    lambda x: f"R${x:,.2f}".replace(",", "X")
                    .replace(".", ",")
                    .replace("X", ".")
                )

                df_soma["total_liquido"] = (
                    df_soma["valor_num"] - df_soma["total_codigos_especiais"]
                )

                df_soma["total_liquido_fmt"] = df_soma["total_liquido"].apply(
                    lambda x: f"R${x:,.2f}".replace(",", "X")
                    .replace(".", ",")
                    .replace("X", ".")
                )

                df_soma = df_soma.sort_values(
                    by="Nome da Filial", key=lambda col: col.map(sort_buffon)
                )

                COLUNAS_ESPECIAIS = {
                    "C-270.4 - INSS": ["901"],
                    "C-147.3 - IRF rec.": ["941"],
                    "C-275.5 - V.T.": ["93", "240"],
                    "C-297.6 - Farm.": ["231"],
                    "C-51.5 - Ad. Sal.": [
                        "30",
                        "31",
                        "32",
                        "33",
                        "34",
                        "35",
                        "36",
                        "37",
                        "38",
                        "150",
                        "151",
                        "152",
                        "153",
                        "154",
                        "155",
                        "156",
                        "157",
                        "158",
                    ],
                    "C-51.5 - Desc. Ad. Sal.": ["44"],
                    "C-2267.5 - Confissao de dívida": ["20053"],
                    "C-142.2 - P.Alim.": ["908"],
                    "C-297.6 - Pl. Saúde": [
                        "233",
                        "241",
                        "242",
                        "262",
                        "20091",
                    ],
                    "C-146.5 - Sind. Rec.": ["933", "11992", "20078", "20088", "20090"],
                    "C-302.6 - Cesta Basica": ["258", "20080"],
                    "D-54.0 - Sal. Fam.": ["907"],
                    "D-53.1 - Sal. Mat.": ["130"],
                    "D-52.3 - ad 13° sal.": ["169", "170", "171", "173"],
                    "C-22667 - D-CAIXA (Desc.emprest. Consig.)": ["20086"],
                }
                # ==========================================================
                # 🔹 Construir opções no formato "codigo - descricao"
                # ==========================================================

                # Criar dicionário: código → descrição
                mapa_codigos = (
                    df_final[["codigo", "descricao"]]
                    .drop_duplicates()
                    .assign(codigo=lambda df: df["codigo"].astype(str))
                    .set_index("codigo")["descricao"]
                    .to_dict()
                )

                # Criar lista de opções formatadas
                opcoes_formatadas = []

                for cod in df_final["codigo"].astype(str).unique():
                    desc = mapa_codigos.get(cod, "")
                    opcoes_formatadas.append(f"{cod} - {desc}")

                # Adicionar também códigos dos defaults já existentes em COLUNAS_ESPECIAIS
                for lista in COLUNAS_ESPECIAIS.values():
                    for cod in lista:
                        if cod not in mapa_codigos:
                            # códigos que vêm apenas do default
                            opcoes_formatadas.append(f"{cod} - (sem descrição)")

                # Remover duplicados mantendo ordem
                opcoes_formatadas = list(dict.fromkeys(opcoes_formatadas))

                # ==========================================================
                # 🔹 Função para converter "codigo - descricao" → apenas "codigo"
                # ==========================================================
                def extrair_codigo(item):
                    return item.split(" - ")[0].strip()

                # ==========================================================
                # 🔹 Renderizar Multiselects (2 colunas)
                # ==========================================================
                with st.expander("Configuração de códigos somados por coluna"):
                    st.markdown(
                        """
As colunas especiais representam grupos de códigos de proventos e descontos que devem ser somados para compor cada categoria exibida na tabela final.  
Cada coluna é formada pela soma dos valores de todos os códigos selecionados ao lado.

Você pode ajustar livremente quais códigos pertencem a cada coluna.  
Qualquer alteração feita aqui afeta diretamente os cálculos da tabela abaixo, incluindo:

- os totais por filial  
- o subtotal (**C-152.0 - sub t**)  
- o salário a pagar (**C-152.0 - Sal. a pagar**)  
- o resultado final (**Resultado**)  
- e todos os totais gerais

Ou seja, esta área define **a lógica de cálculo da planilha**. Cada coluna especial nada mais é do que a soma dos códigos escolhidos para ela.

Por padrão, cada categoria já vem preenchida com os códigos mais utilizados, mas você pode adicionar ou remover códigos conforme necessário.
                    """
                    )
                    col1, col2 = st.columns(2)
                    col_toggle = True
                    codigos_escolhidos = {}

                    for coluna, lista_default_codigos in COLUNAS_ESPECIAIS.items():

                        # Converter defaults para o novo formato
                        defaults_formatados = []
                        for cod in lista_default_codigos:
                            desc = mapa_codigos.get(str(cod), None)
                            if desc is not None:
                                defaults_formatados.append(f"{cod} - {desc}")

                        # Selecionar coluna visual
                        if col_toggle:
                            container = col1
                        else:
                            container = col2
                        with container:
                            with st.expander(f"Códigos para {coluna}"):
                                selecionados_formatados = st.multiselect(
                                    f"Selecione os códigos para **{coluna}**:",
                                    options=opcoes_formatadas,
                                    default=defaults_formatados,
                                    key=f"multi_{coluna}",
                                )

                        # Converter de volta para códigos puros
                        codigos_escolhidos[coluna] = [
                            extrair_codigo(s) for s in selecionados_formatados
                        ]

                        col_toggle = not col_toggle

                    # Atualiza COLUNAS_ESPECIAIS com os valores selecionados
                    COLUNAS_ESPECIAIS = codigos_escolhidos

                # ==========================================================
                # FUNÇÃO PARA SOMAR CÓDIGOS POR FILIAL
                # ==========================================================

                def somar_codigos_por_filial(codigos):
                    codigos_str = set(str(c) for c in codigos)
                    return (
                        df_final[df_final["codigo"].astype(str).isin(codigos_str)]
                        .groupby("filial", as_index=False)["valor_num"]
                        .sum()
                        .rename(columns={"valor_num": "valor"})
                    )

                # ==========================================================
                # GERAR DATAFRAMES INDIVIDUAIS PARA CADA CATEGORIA
                # ==========================================================

                dfs_merged = []

                for nome_coluna, codigos in COLUNAS_ESPECIAIS.items():
                    df_temp = somar_codigos_por_filial(codigos)
                    df_temp.rename(columns={"valor": nome_coluna}, inplace=True)
                    dfs_merged.append(df_temp)

                # ==========================================================
                # MERGE SEGURO (REUTILIZÁVEL)
                # ==========================================================

                def merge_seguro(base, novo):
                    base = base.merge(
                        novo, left_on="Nome da Filial", right_on="filial", how="left"
                    )
                    base = base.drop(columns=["filial"])
                    return base

                # ==========================================================
                # MERGE DE TODAS AS COLUNAS NO DF PRINCIPAL
                # ==========================================================

                for df_temp in dfs_merged:
                    df_soma = merge_seguro(df_soma, df_temp)

                # ==========================================================
                # TRATAR VALORES FALTANTES
                # ==========================================================

                for col in COLUNAS_ESPECIAIS.keys():
                    df_soma[col] = df_soma[col].fillna(0)

                # ==========================================================
                # FORMATAR EM REAIS
                # ==========================================================

                def fmt_real(v):
                    return (
                        f"{v:,.2f}".replace(",", "X")
                        .replace(".", ",")
                        .replace("X", ".")
                    )

                for col in COLUNAS_ESPECIAIS.keys():
                    df_soma[col + "_fmt"] = df_soma[col].apply(fmt_real)

                # ==========================================================
                # MONTAR DATAFRAME FINAL
                # ==========================================================

                colunas_fmt = [c + "_fmt" for c in [*COLUNAS_ESPECIAIS.keys()][0:11]]
                colunas_fmt_2 = [c + "_fmt" for c in [*COLUNAS_ESPECIAIS.keys()][11:14]]
                colunas_fmt_3 = [c + "_fmt" for c in [*COLUNAS_ESPECIAIS.keys()][14:]]

                # Lista das colunas especiais já existentes em df_soma
                colunas_calc_sub_t = list(COLUNAS_ESPECIAIS.keys())[0:11]

                # Converter valores de D-266.6 - Total salário para número
                df_soma["D-266.6_num"] = (
                    df_soma["total_liquido_fmt"]
                    .str.replace("R$", "")
                    .str.replace(".", "")
                    .str.replace(",", ".")
                    .astype(float)
                )

                # Converter valores das colunas especiais para número
                for col in colunas_calc_sub_t:
                    df_soma[col + "_num"] = (
                        df_soma[col + "_fmt"]
                        .str.replace("R$", "")
                        .str.replace(".", "")
                        .str.replace(",", ".")
                        .astype(float)
                    )

                # Subt = Total salário - soma das colunas especiais
                df_soma["C-152.0 - sub t"] = df_soma["D-266.6_num"] - df_soma[
                    [c + "_num" for c in colunas_calc_sub_t]
                ].sum(axis=1)

                # Formatar
                df_soma["C-152.0 - sub t_fmt"] = df_soma["C-152.0 - sub t"].apply(
                    fmt_real
                )

                # ==========================================================
                # NOVA COLUNA: C-152.0 - Sal. a pagar
                # ==========================================================

                # Colunas especiais que devem ser subtraídas
                colunas_salario_a_pagar = list(COLUNAS_ESPECIAIS.keys())[11:14]

                # Converter essas colunas para número (se ainda não tiverem)
                for col in colunas_salario_a_pagar:
                    df_soma[col + "_num"] = (
                        df_soma[col + "_fmt"]
                        .str.replace("R$", "")
                        .str.replace(".", "")
                        .str.replace(",", ".")
                        .astype(float)
                    )

                # Calcular soma das três colunas
                df_soma["soma_especiais_sal_pagar"] = df_soma[
                    [c + "_num" for c in colunas_salario_a_pagar]
                ].sum(axis=1)

                # Calcular Salário a Pagar
                df_soma["C-152.0 - Sal. a pagar"] = (
                    df_soma["C-152.0 - sub t"] + df_soma["soma_especiais_sal_pagar"]
                )

                # Formatar
                df_soma["C-152.0 - Sal. a pagar_fmt"] = df_soma[
                    "C-152.0 - Sal. a pagar"
                ].apply(fmt_real)

                # ==========================================================
                # NOVA COLUNA: RESULTADO
                # resultado = (C-152.0 - Sal. a pagar) - (C-22667 - D-CAIXA ...)
                # ==========================================================

                col_dcaixa = list(COLUNAS_ESPECIAIS.keys())[14]

                # Converter a coluna D-CAIXA para número
                df_soma[col_dcaixa + "_num"] = (
                    df_soma[col_dcaixa + "_fmt"]
                    .str.replace("R$", "")
                    .str.replace(".", "")
                    .str.replace(",", ".")
                    .astype(float)
                )

                # Calcular o resultado final
                df_soma["Resultado"] = (
                    df_soma["C-152.0 - Sal. a pagar"] - df_soma[col_dcaixa + "_num"]
                )

                # Formatar para R$
                df_soma["Resultado_fmt"] = df_soma["Resultado"].apply(fmt_real)

                df_resumo = df_soma[
                    [
                        "Filial",
                        "total_proventos",
                        "total_codigos_especiais_fmt",
                        "total_liquido_fmt",
                    ]
                    + colunas_fmt
                    + ["C-152.0 - sub t_fmt"]
                    + colunas_fmt_2
                    + ["C-152.0 - Sal. a pagar_fmt"]
                    + colunas_fmt_3
                    + ["Resultado_fmt"]
                ].rename(
                    columns={
                        "total_proventos": "Total proventos",
                        "total_codigos_especiais_fmt": "Total proventos e descontos selecionados",
                        "total_liquido_fmt": "D-266.6 - Total salário",
                        **{c + "_fmt": c for c in COLUNAS_ESPECIAIS.keys()},
                        "C-152.0 - sub t_fmt": "C-152.0 - sub t",
                        "C-152.0 - Sal. a pagar_fmt": "C-152.0 - Sal. a pagar",
                        "Resultado_fmt": "Resultado",
                    }
                )

                df_resumo.reset_index(drop=True, inplace=True)

                mostrar_proventos = st.toggle(
                    "Mostrar valores utilizadas para calculo de salário", value=False
                )

                df_resumo_view = df_resumo.copy()

                if not mostrar_proventos:
                    df_resumo_view = df_resumo_view.drop(
                        ["Total proventos", "Total proventos e descontos selecionados"],
                        axis=1,
                    )
                for col in df_resumo_view.columns:
                    if (
                        df_resumo_view[col].dtype == object
                        and df_resumo_view[col].str.contains("R\$").any()
                    ):
                        df_resumo_view[col] = df_resumo_view[col].str.replace(
                            "R$", "", regex=False
                        )

                df_totais = df_resumo_view.copy()

                # Identificar colunas numéricas que estão no formato R$
                colunas_monetarias = [
                    col
                    for col in df_totais.columns
                    if df_totais[col].dtype == object
                    and df_totais[col].str.contains(",").any()
                ]

                # Converter temporariamente para float
                for col in colunas_monetarias:
                    df_totais[col + "_num"] = (
                        df_totais[col]
                        .str.replace(".", "")
                        .str.replace(",", ".")
                        .astype(float)
                    )

                # Criar dicionário da linha de totais
                linha_total = {"Filial": "", "Filial": "TOTAL GERAL"}

                # Para cada coluna monetária, soma
                for col in colunas_monetarias:
                    total = df_totais[col + "_num"].sum()
                    linha_total[col] = (
                        f"{total:,.2f}".replace(",", "X")
                        .replace(".", ",")
                        .replace("X", ".")
                    )

                # Outras colunas numéricas não-R$ (se existirem)
                colunas_numericas = [
                    col
                    for col in df_totais.select_dtypes(include=["number"]).columns
                    if col.endswith("_num") is False
                ]

                for col in colunas_numericas:
                    linha_total[col] = df_totais[col].sum()

                # Adicionar linha ao final do dataframe
                df_totais = df_totais[list(df_resumo_view.columns)].copy()
                df_totais.loc[len(df_totais)] = linha_total

                df_totais.set_index("Filial", inplace=True)

                def bold_last_row(row):
                    return [
                        "font-weight: bold" if row.name == "TOTAL GERAL" else ""
                        for _ in row
                    ]

                df_resumo_styled = df_totais.style.set_table_styles(
                    [
                        {
                            "selector": "th.row_heading",
                            "props": [("min-width", "200px")],
                        },
                        {
                            "selector": "th.col_heading",
                            "props": [("min-width", "200px")],
                        },
                    ]
                ).apply(bold_last_row, axis=1)
                # Exibir tabela com linha de total
                st.dataframe(df_resumo_styled, use_container_width=True)

                st.subheader("Resumo Prolabore")
                st.write("")

                # --- Tabela Prolabore / INSS / Total Líquido ---

                # Filtrar valores
                df_prolabore = (
                    df_final[df_final["codigo"] == 17]
                    .groupby("filial")["valor_num"]
                    .sum()
                    .reset_index()
                )
                df_prolabore.rename(columns={"valor_num": "prolabore"}, inplace=True)

                df_inss = (
                    df_final[df_final["codigo"] == 940]
                    .groupby("filial")["valor_num"]
                    .sum()
                    .reset_index()
                )
                df_inss.rename(columns={"valor_num": "inss"}, inplace=True)

                # Unir prolabore + inss em uma só tabela
                df_extra = pd.merge(
                    df_prolabore, df_inss, on="filial", how="outer"
                ).fillna(0)

                # Calcular total líquido
                df_extra["total_liquido"] = df_extra["prolabore"] - df_extra["inss"]

                # 🔥 Criar linha de total geral
                total_prolabore = df_extra["prolabore"].sum()
                total_inss = df_extra["inss"].sum()
                total_liquido = df_extra["total_liquido"].sum()

                df_total = pd.DataFrame(
                    {
                        "filial": ["TOTAL GERAL"],
                        "prolabore": [total_prolabore],
                        "inss": [total_inss],
                        "total_liquido": [total_liquido],
                    }
                )

                # Adicionar a linha ao dataframe
                df_extra = pd.concat([df_extra, df_total], ignore_index=True)

                # Formatar valores
                df_extra_fmt = df_extra.copy()
                df_extra_fmt["prolabore"] = df_extra_fmt["prolabore"].apply(fmt_real)
                df_extra_fmt["inss"] = df_extra_fmt["inss"].apply(fmt_real)
                df_extra_fmt["total_liquido"] = df_extra_fmt["total_liquido"].apply(
                    fmt_real
                )

                # Ordenar mantendo TOTAL GERAL no final
                df_extra_fmt["__ordem__"] = df_extra_fmt["filial"].apply(
                    lambda x: (999, "") if x == "TOTAL GERAL" else sort_buffon(x)
                )
                df_extra_fmt = df_extra_fmt.sort_values("__ordem__").drop(
                    columns="__ordem__"
                )

                # Renomear colunas
                df_extra_fmt.rename(
                    columns={
                        "filial": "Filial",
                        "prolabore": "Prolabore",
                        "inss": "INSS",
                        "total_liquido": "Total Líquido",
                    },
                    inplace=True,
                )

                df_extra_fmt["Filial"] = df_extra_fmt["Filial"].apply(mapear_filial)

                df_extra_fmt.set_index("Filial", inplace=True)

                df_extra_fmt_styled = df_extra_fmt.style.set_table_styles(
                    [
                        {
                            "selector": "th.row_heading",
                            "props": [("min-width", "200px")],
                        },
                        {
                            "selector": "th.col_heading",
                            "props": [("min-width", "200px")],
                        },
                    ]
                ).apply(bold_last_row, axis=1)

                st.dataframe(df_extra_fmt_styled, use_container_width=True)

            # ===============================
            # 🔹 DOWNLOADS
            # ===============================
            output = io.BytesIO()

            # --- Preparar df_totais para download ---
            df_download_totais = df_totais.reset_index().copy()

            # --- Preparar df_extra ---
            df_download_extra = df_extra_fmt.reset_index().copy()

            df_download_extra = df_download_extra.sort_values(
                by="Filial", key=lambda col: col.map(sort_buffon)
            )

            HEADER_NUMBERS = {
                "C-270.4 - INSS": "10",
                "C-147.3 - IRF rec.": "11",
                "C-275.5 - V.T.": "12",
                "C-297.6 - Farm.": "13",
                "C-51.5 - Ad. Sal.": "90",
                "C-51.5 - Desc. Ad. Sal.": "91",
                "C-2267.5 - Confissao de dívida": "150",
                "C-142.2 - P.Alim.": "15",
                "C-297.6 - Pl. Saúde": "16",
                "C-146.5 - Sind. Rec.": "17",
                "C-302.6 - Cesta Basica": "18",
                "C-152.0 - sub t": "19",
                "C-22667 - D-CAIXA (Desc.emprest. Consig.)": "152",
            }

            # Create Excel with 2 sheets
            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:

                df_download_totais.to_excel(
                    writer, index=False, sheet_name="Resumo Salários", startrow=3
                )
                df_download_extra.to_excel(
                    writer, index=False, sheet_name="Calculo Prolabore"
                )

                # --------------------------------------
                # 🔹 Add Titles to "Resumo Salários"
                # --------------------------------------
                workbook = writer.book
                worksheet = writer.sheets["Resumo Salários"]

                format_title = workbook.add_format(
                    {
                        "bold": True,
                        "align": "left",
                        "valign": "vcenter",
                        "font_size": 14,
                    }
                )
                format_sub = workbook.add_format(
                    {
                        "bold": True,
                        "align": "left",
                        "valign": "vcenter",
                        "font_size": 12,
                    }
                )

                fmt_num = workbook.add_format(
                    {
                        "align": "center",
                        "valign": "vcenter",
                        "bold": True,
                    }
                )

                fmt_cont_cods = workbook.add_format(
                    {
                        "align": "left",
                        "valign": "vcenter",
                        "bold": True,
                    }
                )

                col_names = df_download_totais.columns.tolist()

                for col_idx, col_name in enumerate(col_names):
                    numero = HEADER_NUMBERS.get(col_name, "")
                    worksheet.write(2, col_idx, numero, fmt_num)

                worksheet.merge_range("A3:B3", "Códigos contábeis", fmt_cont_cods)

                # Write titles
                worksheet.merge_range(
                    "A1:G1", "COMERCIAL BUFFON COMB. E TRANSPORTES LTDA", format_title
                )

                # Use previous month (MM/YYYY)
                first_day_this_month = datetime.now().replace(day=1)
                last_day_prev_month = first_day_this_month - timedelta(days=1)
                mes_ano_excel = last_day_prev_month.strftime("%m/%Y")

                worksheet.merge_range(
                    "A2:G2", f"SALÁRIOS REFERENTES MÊS {mes_ano_excel}", format_sub
                )

                last_fmt = workbook.add_format({"bold": True})

                # Descobrir número total de linhas do DF
                last_row = len(df_download_totais)

                # Como seu DF começa em startrow=1, somamos +1
                excel_row = last_row + 3

                # Tornar toda a linha em bold
                worksheet.set_row(excel_row, None, last_fmt)

            # Save bytes
            xlsx_data = output.getvalue()

            # --- Filename with previous month ---
            mes_ano = last_day_prev_month.strftime("%m-%Y")
            nome_arquivo = f"resumo_salarios_buffon_{mes_ano}.xlsx"

            # Download button
            st.download_button(
                label=":material/download: Baixar",
                data=xlsx_data,
                file_name=nome_arquivo,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
            )

        except Exception as e:
            st.error("Ocorreu um erro ao processar os dados extraídos.")
            print(f"[ERRO] - {e}")
