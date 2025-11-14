import streamlit as st
import pandas as pd
import io
import csv
import re


def sort_filial(value):
    value = str(value).strip()

    # Put "Matriz" always first
    if value.lower() == "matriz":
        return (0, 0)

    # Match "Buffon X"
    m = re.match(r"Buffon\s+(\d+)", value)
    if m:
        return (1, int(m.group(1)))  # Sort by numeric value

    # Everything else goes after
    return (2, value)


def sort_tipo(value):
    order = {
        "Provento": 0,
        "Desconto": 1,
    }
    return order.get(value, 99)


st.set_page_config(
    page_title="JC Contabilidade - Postos Buffon", layout="wide"
)

st.title("🧾 JC Contabilidade - Postos Buffon")

with st.container(border=True):
    st.header("Carregar tabela de salários")
    st.write(
        "Envie aqui o arquivo **CSV original** recebido por e-mail."
        "O sistema faz a leitura automática do formato e extrai as informações contábeis."
    )
    uploaded_file = st.file_uploader("Selecione o arquivo CSV", type=["csv"])

    if uploaded_file is not None:
        try:
            uploaded_file.seek(0)
            uploaded_file = io.BytesIO(uploaded_file.read())
            # Detecta delimitador automaticamente
            content = uploaded_file.getvalue().decode("utf-8", errors="ignore")
            sniffer = csv.Sniffer()
            delimiter = sniffer.sniff(content.splitlines()[0]).delimiter

            # Lê o CSV
            df = pd.read_csv(
                io.StringIO(content),
                delimiter=delimiter,
                engine="python",
                on_bad_lines="skip",
                header=None,
            )

            # Limpeza básica
            df = df.dropna(axis=1, how="all")
            df = df.dropna(axis=0, how="all")
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
            # Junta colunas da H em diante
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

            # Regex para extrair as informações
            def extrair_info(texto):
                texto = str(texto)
                padrao = re.compile(
                    r"^(?P<descricao>.*)\s+(?P<valor>\d+(?:[.,]\d{2}))\s+(?P<nome>.+?)\s+(?P<divisor>-\d+)\s+(?P<filial>[A-Za-z0-9\s]+)\s+(?P<cnpj>\d{14})\s+(?P<digito>[A-Z])$"
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

            # Extrai os campos
            extraidos = (
                df["Informações_Complementares"].apply(extrair_info).apply(pd.Series)
            )
            df_final = pd.concat(
                [df.drop(columns=["Informações_Complementares"]), extraidos], axis=1
            )

            # Converte valor numérico
            df_final["valor_num"] = (
                df_final["valor"]
                .astype(str)
                .str.replace(",", ".")
                .astype(float, errors="ignore")
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

            # 🔹 REMOVE LINHAS COM DIGITO 'P' E CÓDIGOS ESPECÍFICOS
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

            st.success("Normalização e extração concluídas ✅")
        except Exception as e:
            st.error(
                "O arquivo enviado não corresponde ao padrão esperado. "
                "Certifique-se de utilizar o CSV original recebido por e-mail ou contate o suporte."
            )
            st.stop()
    else:
        st.info("Envie um arquivo CSV para começar.")

if uploaded_file is not None and "df_final" in locals():
    with st.container(border=True):
        st.header("Resultados da extração")

        try:

            tabs = st.tabs(["Dados Extraídos", "Proventos por filial"])

            with tabs[0]:
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
                df_table = df_table.sort_values(
                    by=["filial", "digito"],
                    key=lambda col: (
                        col.map(sort_filial)
                        if col.name == "filial"
                        else col.map(sort_tipo)
                    ),
                )

                col1, col2 = st.columns(2)

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

                df_filtrado = df_table.copy()

                if len(filiais_selecionadas) > 0:
                    df_filtrado = df_filtrado[
                        df_filtrado["filial"].isin(filiais_selecionadas)
                    ]

                if len(tipos_selecionados) > 0:
                    df_filtrado = df_filtrado[
                        df_filtrado["digito"].isin(tipos_selecionados)
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
            # 🔹 SOMA POR FILIAL (considerando filtro e dígito D)
            # ===============================
            with tabs[1]:
                st.markdown(
                    "Aqui você vê a soma dos **proventos** por filial e também pode selecionar "
                    "**códigos específicos** de proventos e descontos para diminuir do total de proventos."
                )
                df_soma = (
                    df_final[df_final["digito"] == "P"]
                    .groupby("filial", as_index=False)["valor_num"]
                    .sum()
                )

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
                codigos_D_padrao = ["3", "6", "19", "22", "23", "911", "938"]

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

                # 🔹 filtrar somente as opções de cada tipo
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
                    "Selecionar códigos de proventos e descontos para ajuste do total líquido"
                ):
                    st.write(
                        "Os códigos listados abaixo permitem ajustar o cálculo do **total líquido** "
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
                    # Converter "código – descrição" → código
                    codigos_P_selecionados = [
                        codigo_map[x] for x in codigos_P_select_fmt
                    ]

                with colD:
                    codigos_D_select_fmt = st.multiselect(
                        "Códigos de descontos:",
                        options=codigos_D_formatados,
                        default=codigos_D_default_fmt,
                    )
                    # Converter "código – descrição" → código
                    codigos_D_selecionados = [
                        codigo_map[x] for x in codigos_D_select_fmt
                    ]

                st.markdown(
                    "<hr style='padding:4px 0 0 0;margin:0;'>", unsafe_allow_html=True
                )

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

                df_soma = df_soma.merge(df_codigos_especiais, on="filial", how="left")

                df_soma["total_codigos_especiais"] = df_soma[
                    "total_codigos_especiais"
                ].apply(
                    lambda x: (
                        f"R${x:,.2f}".replace(",", "X")
                        .replace(".", ",")
                        .replace("X", ".")
                        if pd.notnull(x)
                        else "R$0,00"
                    )
                )

                # Criar coluna numérica real para cálculo
                df_soma["total_proventos_num"] = (
                    df_soma["total_proventos"]
                    .str.replace("R$", "")
                    .str.replace(".", "")
                    .str.replace(",", ".")
                    .astype(float)
                )
                df_soma["total_codigos_especiais_num"] = (
                    df_soma["total_codigos_especiais"]
                    .str.replace("R$", "")
                    .str.replace(".", "")
                    .str.replace(",", ".")
                    .astype(float)
                )

                # Novo total líquido = Proventos – Códigos Selecionados
                df_soma["total_liquido_num"] = (
                    df_soma["total_proventos_num"]
                    - df_soma["total_codigos_especiais_num"]
                )

                # Converter para formato monetário
                df_soma["total_liquido"] = df_soma["total_liquido_num"].apply(
                    lambda x: f"R${x:,.2f}".replace(",", "X")
                    .replace(".", ",")
                    .replace("X", ".")
                )

                # Selecionar colunas finais
                df_soma = df_soma[
                    [
                        "filial",
                        "total_proventos",
                        "total_codigos_especiais",
                        "total_liquido",
                    ]
                ]

                df_soma = df_soma.sort_values(
                    by="filial", key=lambda col: col.map(sort_filial)
                )

                filiais_opcoes = sorted(
                    df_soma["filial"].dropna().unique(), key=sort_filial
                )
                filiais_selecionadas = st.multiselect(
                    "Filtrar por Filial:",
                    filiais_opcoes,
                    default=None,
                    placeholder="Selecione uma ou mais filiais",
                    key="soma_filiais",
                )

                df_filtrado = df_soma.copy()

                if len(filiais_selecionadas) > 0:
                    df_filtrado = df_filtrado[
                        df_filtrado["filial"].isin(filiais_selecionadas)
                    ]

                df_filtrado = df_filtrado.rename(
                    columns={
                        "filial": "Filial",
                        "total_proventos": "Total proventos",
                        "total_codigos_especiais": "Total proventos e descontos selecionados",
                        "total_liquido": "Total líquido (Proventos – Selecionados)",
                    }
                )
                df_filtrado.reset_index(drop=True, inplace=True)

                st.dataframe(df_filtrado, use_container_width=True)

                st.markdown(
                    "<hr style='padding:4px 0 0 0;margin:0;'>", unsafe_allow_html=True
                )

                # Garantir que estamos usando a versão filtrada
                df_metricas = df_filtrado.copy()

                # Converter para números reais
                df_metricas["total_proventos_num"] = (
                    df_metricas["Total proventos"]
                    .str.replace("R$", "")
                    .str.replace(".", "")
                    .str.replace(",", ".")
                    .astype(float)
                )

                df_metricas["total_codigos_num"] = (
                    df_metricas["Total proventos e descontos selecionados"]
                    .str.replace("R$", "")
                    .str.replace(".", "")
                    .str.replace(",", ".")
                    .astype(float)
                )

                df_metricas["total_liquido_num"] = (
                    df_metricas["Total líquido (Proventos – Selecionados)"]
                    .str.replace("R$", "")
                    .str.replace(".", "")
                    .str.replace(",", ".")
                    .astype(float)
                )

                # Cálculos
                soma_total_proventos = df_metricas["total_proventos_num"].sum()
                soma_total_codigos = df_metricas["total_codigos_num"].sum()
                soma_total_liquido = df_metricas["total_liquido_num"].sum()
                qtd_filiais = len(df_metricas)

                # Formatação
                fmt = (
                    lambda x: f"R${x:,.2f}".replace(",", "X")
                    .replace(".", ",")
                    .replace("X", ".")
                )

                colA, colB, colC, colD = st.columns(4)

                colA.metric("Quantidade de filiais consideradas", qtd_filiais)
                colB.metric("Soma total dos proventos", fmt(soma_total_proventos))
                colC.metric(
                    "Soma total das reduções selecionadas", fmt(soma_total_codigos)
                )
                colD.metric("Total líquido geral", fmt(soma_total_liquido))

                # ===============================
                # 🔹 DOWNLOADS
                # ===============================
                output = io.BytesIO()

                with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                    df_soma.to_excel(writer, index=False, sheet_name="Soma por Filial")

                # Conteúdo do arquivo
                xlsx_data = output.getvalue()

                st.download_button(
                    label="📥 Baixar Soma por Filial",
                    data=xlsx_data,
                    file_name="soma_por_filial.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
        except Exception as e:
            st.error(
                "Ocorreu um erro ao processar os dados extraídos. Por favor, tente novamente ou contate o suporte."
            )
