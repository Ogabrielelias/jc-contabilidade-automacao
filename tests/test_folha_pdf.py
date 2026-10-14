import unittest
from decimal import Decimal
from pathlib import Path

from folha_pdf import extrair_detalhes_pdf, extrair_resumos_paginas, extrair_resumos_pdf


class ResumosPdfTest(unittest.TestCase):
    def test_continuacoes_sem_duplicar_ou_incluir_total_empresa(self):
        linhas = extrair_resumos_paginas([
            "Estabelecimento: 1026 - Buffon 26\nVencimento",
            "Estabelecimento: 1026 - Buffon 26\nVlr. FGTS:\n8.000,25",
            "Estabelecimento: 1026 - Buffon 26\nContratos Ativos: 51\n"
            "Contratos Afastados: 1\nContratos Rescindidos: 3",
            "Totais da Empresa: 1001\nContratos Ativos: 999\nVlr. FGTS: 99.999,00",
        ])
        self.assertEqual(linhas, [
            {"Filial": "Filial 25", "Func.": 51, "Salário": "8.000,25"}
        ])

    def test_continuacao_antiga_e_resumo_geral(self):
        linhas = extrair_resumos_paginas([
            "Mensal + 13º Salário 999,00",  # sem filial: ignorar
            "RESUMO Filial: 2",
            "Nesta Folha\n23\nMensal + 13º Salário 4.655,78",
            "RESUMO Matriz: 1",
            "RESUMO DO PERÍODO",
            "Nesta Folha\n2615\nMensal + 13º Salário 483.623,97",
        ])
        self.assertEqual(linhas, [
            {"Filial": "Filial 1", "Func.": 23, "Salário": "4.655,78"},
            {"Filial": "Matriz", "Func.": None},
        ])

    def test_zero_e_matriz_nova(self):
        self.assertEqual(extrair_resumos_paginas([
            "Estabelecimento: 1001 - Buffon 01\nContratos Ativos: 0\n"
            "Contratos Afastados: 0\nVlr. FGTS: 0,00"
        ]), [{"Filial": "Matriz", "Func.": 0, "Salário": "0,00"}])

    def ler_exemplo(self, nome):
        caminho = Path(__file__).resolve().parents[1] / nome
        if not caminho.exists():
            self.skipTest("PDF de exemplo não disponível neste checkout")
        return extrair_resumos_pdf(caminho.read_bytes())

    def test_pdf_novo_completo(self):
        linhas = self.ler_exemplo("Buffon Folha de salário 09 2026.pdf")
        self.assertEqual(len(linhas), 116)
        self.assertEqual(len({r["Filial"] for r in linhas}), 116)
        self.assertEqual(sum(r["Func."] for r in linhas), 2566)
        total_fgts = sum(
            Decimal(r["Salário"].replace(".", "").replace(",", "."))
            for r in linhas
        )
        self.assertEqual(total_fgts, Decimal("576586.48"))
        filial_25 = next(r for r in linhas if r["Filial"] == "Filial 25")
        self.assertEqual(filial_25["Func."], 51)
        self.assertEqual(linhas[0]["Salário"], "13.545,65")

    def test_pdf_antigo_completo(self):
        linhas = self.ler_exemplo("Folha Resumo Salário Buffon 09 2025.pdf")
        self.assertEqual(len(linhas), 111)
        self.assertEqual(sum(r["Func."] for r in linhas), 2615)
        self.assertEqual(linhas[-1], {"Filial": "Matriz", "Func.": 15})

    def test_detalhes_conferem_com_totais_impressos(self):
        caminho = Path(__file__).resolve().parents[1] / "Buffon Folha de salário 09 2026.pdf"
        if not caminho.exists():
            self.skipTest("PDF de exemplo não disponível neste checkout")
        dados = extrair_detalhes_pdf(caminho.read_bytes())
        self.assertEqual(len(dados["eventos"]), 7121)
        self.assertEqual(len(dados["resumos"]), 117)
        self.assertEqual(dados["documento"][0]["Início"], "01/09/2026")
        decimal = lambda valor: Decimal(valor.replace(".", "").replace(",", "."))
        for resumo in dados["resumos"]:
            unidade = resumo["Unidade"]
            eventos = [e for e in dados["eventos"] if e["Unidade"] == unidade]
            for tipo, total in (("Vencimento", "Total Venc."), ("Desconto", "Total Desc.")):
                self.assertEqual(
                    sum(decimal(e["Valor"]) for e in eventos if e["Tipo"] == tipo),
                    decimal(resumo[total]), (unidade, tipo),
                )
            self.assertEqual(
                decimal(resumo["Total Venc."]) - decimal(resumo["Total Desc."]),
                decimal(resumo["Líquido"]), unidade,
            )
            self.assertEqual(
                sum(c["Contratos"] for c in dados["categorias"] if c["Unidade"] == unidade),
                resumo["Ativos + afastados"], unidade,
            )

    def test_detalhes_layout_antigo_nao_aplicavel(self):
        caminho = Path(__file__).resolve().parents[1] / "Folha Resumo Salário Buffon 09 2025.pdf"
        if not caminho.exists():
            self.skipTest("PDF de exemplo não disponível neste checkout")
        self.assertFalse(extrair_detalhes_pdf(caminho.read_bytes())["documento"])


if __name__ == "__main__":
    unittest.main()
