import io
import unittest
from decimal import Decimal
from pathlib import Path

import fitz
import openpyxl
import pandas as pd

from folha_adiantamento_13 import (
    extrair_adiantamento_13, tabela_adiantamento_13, escrever_adiantamento_13,
)

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "Buffon adiantamento 13° salário 09 2026.pdf"


class Adiantamento13Test(unittest.TestCase):
    def pdf(self, texto):
        with fitz.open() as doc:
            doc.new_page().insert_text((30, 30), texto)
            return doc.tobytes()

    def test_outro_relatorio_nao_e_identificado_como_adiantamento(self):
        self.assertIsNone(extrair_adiantamento_13(self.pdf("Provisao de salario")))

    def test_resumo_incompleto_nao_vira_zero(self):
        with self.assertRaisesRegex(ValueError, "ausente"):
            extrair_adiantamento_13(self.pdf(
                "00030001 - 13 Salario\nFolhas de 01/09/2026 a 30/09/2026\n"
                "Estabelecimento: 1001 - Buffon 01\nVlr. FGTS: 0,00"
            ))

    @unittest.skipUnless(PDF.exists(), "PDF de exemplo ausente")
    def test_valores_reconciliam_sem_duplicar_total_empresa(self):
        dados = extrair_adiantamento_13(PDF.read_bytes())
        self.assertEqual(dados["competencia"], "09/2026")
        self.assertEqual(len(dados["registros"]), 15)
        for coluna, total in (
            ("Ad 13 Sal.", "32269.45"), ("Fgts s/ 13 sal.", "2581.47")
        ):
            self.assertEqual(
                sum(r[coluna] for r in dados["registros"].values()), Decimal(total)
            )
        self.assertEqual(dados["registros"]["Filial 116"]["Ad 13 Sal."], Decimal("2766.07"))
        tabela = tabela_adiantamento_13(dados, ["Matriz", "Filial 3"])
        self.assertEqual(tabela["Filial"][:4].tolist(), ["F05", "F07", "F17", "F18"])
        self.assertEqual(len(tabela), 16)
        self.assertEqual(tabela.iloc[-1].tolist(), ["TOTAL GERAL", 32269.45, 2581.47])
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            escrever_adiantamento_13(writer, dados)
        aba = openpyxl.load_workbook(io.BytesIO(output.getvalue())).active
        self.assertEqual(aba["A1"].value, "COMERCIAL BUFFON COMB. E TRANSPORTES LTDA")
        self.assertEqual(aba["A2"].value, "Com Buffon / Ad 13 sal / FGTS - 09/2026")
        self.assertEqual(aba["B4"].value, "D-52.3 ad 13 sal")
        self.assertEqual(aba["B5"].value, "C-2478.3 13 a pg")
        self.assertEqual(aba["C4"].value, "D-271.2 FGTS")
        self.assertEqual(aba["C5"].value, "C-145.7 FGTS a pg")
        self.assertEqual(aba["B6"].value, 7117.99)
        self.assertEqual(aba["C6"].value, 569.42)
        self.assertEqual(aba["B6"].number_format, "#,##0.00")
        self.assertEqual(list(aba.values)[-1][:3], ("TOTAL GERAL", '=SUM(B6:B20)', '=SUM(C6:C20)'))
        valores = openpyxl.load_workbook(io.BytesIO(output.getvalue()), data_only=True).active
        self.assertEqual(list(valores.values)[-1][:3], ("TOTAL GERAL", 32269.45, 2581.47))
