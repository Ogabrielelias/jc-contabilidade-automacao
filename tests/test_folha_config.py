import unittest

from folha_config import COLUNAS_PDF, config_pdf_inicial, dataframe_lancamentos_pdf, normalizar_config_pdf


class ConfigPdfTest(unittest.TestCase):
    def test_normaliza_codigos_e_preserva_ordem_contabil(self):
        config = normalizar_config_pdf({
            "configurado": True, "codigos_padrao": [1, "00000001", "50001"],
            "colunas_especiais": {COLUNAS_PDF[0]: ["63101"]},
        })
        self.assertEqual(config["codigos_padrao"], ["00000001", "00050001"])
        self.assertEqual(list(config["colunas_especiais"]), COLUNAS_PDF)
        self.assertEqual(config["colunas_especiais"][COLUNAS_PDF[0]], ["00063101"])
        self.assertTrue(config["configurado"])

    def test_config_inicial_aplica_padroes_informados(self):
        config = config_pdf_inicial()
        self.assertFalse(config["configurado"])
        self.assertEqual(config["prolabore"], ["00001501"])
        self.assertEqual(config["inss_prolabore"], ["00063401"])
        self.assertEqual(config["colunas_especiais"]["C-270.4 - INSS"], ["00063101"])
        self.assertEqual(config["colunas_especiais"]["D-53.1 - Sal. Mat."],
                         ["00000040", "00000043", "00000044", "00000045", "00000046", "00000048"])
        self.assertEqual(config["colunas_especiais"]["D-52.3 - Ad 13° Sal."], [])
        config["codigos_padrao"].append("00000001")
        self.assertEqual(config_pdf_inicial()["codigos_padrao"], [])

    def test_lista_salva_vazia_nao_e_reposta_pelo_padrao(self):
        config = normalizar_config_pdf({"colunas_especiais": {"C-270.4 - INSS": []}})
        self.assertEqual(config["colunas_especiais"]["C-270.4 - INSS"], [])
        self.assertEqual(config["colunas_especiais"]["C-147.3 - IRF rec."], ["00064101"])

    def test_rejeita_codigo_invalido(self):
        for codigo in ("1.0", "ABC", "123456789", "-1"):
            with self.assertRaises(ValueError):
                normalizar_config_pdf({"prolabore": [codigo]})

    def test_adaptacao_exclui_bases_totais_e_vencimentos_configurados(self):
        def evento(tipo, codigo, unidade="Matriz"):
            return {"Tipo": tipo, "Código": codigo, "Descrição": "Evento",
                    "Unidade": unidade, "Valor": "1.234,56"}
        dados = {"eventos": [
            evento("Vencimento", "00000001"), evento("Desconto", "00063101"),
            evento("Base", "00099100"), evento("Vencimento", "00000001", "Total da empresa"),
        ]}
        config = config_pdf_inicial()
        df = dataframe_lancamentos_pdf(dados, config)
        self.assertEqual(df["digito"].tolist(), ["P", "D"])
        self.assertEqual(df["valor_num"].tolist(), [1234.56, 1234.56])
        config["excluir_proventos"] = ["00000001"]
        df = dataframe_lancamentos_pdf(dados, config)
        self.assertEqual(df["codigo"].tolist(), ["00063101"])
