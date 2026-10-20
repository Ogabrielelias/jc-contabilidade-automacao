import streamlit as st

from folha_config import CHAVE_CONFIG_PDF, COLUNAS_PDF, normalizar_config_pdf


def configurar_pdf(dados, config, salvar):
    config = normalizar_config_pdf(config)
    catalogo = {
        e["Código"]: f"{e['Código']} - {e['Descrição']} ({e['Tipo']})"
        for e in dados["eventos"]
        if e["Tipo"] != "Base"
    }
    with st.expander(
        "Configuração de códigos somados por coluna", expanded=not config["configurado"]
    ):
        st.write(
            "Associe os códigos do novo sistema às colunas contábeis. "
            "As escolhas são salvas separadamente das configurações do CSV. "
            "Os eventos de base e o consolidado da empresa não entram nos lançamentos."
        )
        if not config["configurado"]:
            st.warning(
                "Primeiro uso: revise os códigos padrão, complete os demais grupos e salve para gerar os resumos."
            )
        with st.form("config_eventos_pdf", border=False):
            nova = {**config, "colunas_especiais": {}}

            def escolher(rotulo, valores, chave):
                opcoes = sorted(set(catalogo) | set(valores))
                return st.multiselect(
                    rotulo,
                    options=opcoes,
                    default=valores,
                    format_func=lambda c: catalogo.get(c, f"{c} - ausente neste PDF"),
                    key=f"pdf_v1_{chave}",
                    accept_new_options=True,
                    help="Selecione eventos ou digite um código numérico de até 8 dígitos para meses futuros.",
                )

            col1, col2 = st.columns(2)
            with col1:
                with st.expander("Códigos para cálculo da D-266.6 - T. Salário"):
                    nova["codigos_padrao"] = escolher(
                        "Selecione os códigos para **D-266.6 - T. Salário**",
                        config["codigos_padrao"],
                        "salario",
                    )
            # Mesma distribuição do padrão antigo: salário à esquerda,
            # primeira coluna contábil à direita e demais grupos alternados.
            for indice, coluna in enumerate(COLUNAS_PDF):
                with col2 if indice % 2 == 0 else col1:
                    with st.expander(f"Códigos para {coluna}"):
                        nova["colunas_especiais"][coluna] = escolher(
                            f"Selecione os códigos para **{coluna}**:",
                            config["colunas_especiais"][coluna],
                            coluna,
                        )
            with col1:
                with st.expander("Códigos para pró-labore"):
                    nova["prolabore"] = escolher(
                        "Eventos de pró-labore", config["prolabore"], "prolabore"
                    )
            with col2:
                with st.expander("Códigos para INSS do pró-labore"):
                    nova["inss_prolabore"] = escolher(
                        "INSS do pró-labore", config["inss_prolabore"], "inss_prolabore"
                    )
            enviada = st.form_submit_button(
                "Salvar configuração e calcular", type="primary"
            )
        if enviada:
            nova["configurado"] = True
            nova = normalizar_config_pdf(nova)
            if salvar(CHAVE_CONFIG_PDF, nova):
                st.toast("Configuração do PDF salva.")
                return nova
            st.error(
                "Não foi possível salvar. A configuração anterior continua em uso; tente novamente."
            )
    return config
