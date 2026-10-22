"""Avaliador restrito para testar as fórmulas emitidas, sem depender do cache.

Não substitui a validação em Excel/LibreOffice. Rejeita sintaxe não suportada.
"""
import ast
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache

from openpyxl.formula.tokenizer import Tokenizer


def calcular(workbook):
    def itens(args):
        for arg in args:
            if isinstance(arg, list):
                yield from arg
            else:
                yield arg

    def soma(*args):
        return sum(v for v in itens(args) if isinstance(v, (float, int)))

    def sumifs(valores, *criterios):
        return sum(v for i, v in enumerate(valores)
                   if all(str(criterios[j][i]).casefold() == str(criterios[j+1]).casefold()
                          for j in range(0, len(criterios), 2)))

    @lru_cache(None)
    def ler(aba, endereco):
        if '!' in endereco:
            aba, endereco = endereco.rsplit('!', 1)
            aba = aba.strip("'").replace("''", "'")
        endereco = endereco.replace('$', '')
        if ':' in endereco:
            return [ler(aba, c.coordinate) for linha in workbook[aba][endereco] for c in linha]
        valor = workbook[aba][endereco].value
        if not isinstance(valor, str) or not valor.startswith('='):
            return '' if valor is None else valor
        exp = []
        for token in Tokenizer(valor).items:
            if token.type == 'WHITE-SPACE':
                continue
            if token.type == 'OPERAND':
                if token.subtype == 'RANGE':
                    exp.append(f'REF({token.value!r})')
                elif token.subtype == 'TEXT':
                    exp.append(repr(token.value[1:-1].replace('""', '"')))
                elif token.subtype == 'NUMBER':
                    exp.append(token.value)
                else:
                    raise AssertionError(token)
            elif token.type == 'FUNC':
                exp.append(token.value)
            elif token.type in ('PAREN', 'SEP'):
                exp.append(token.value)
            elif token.type.startswith('OPERATOR') and token.value in ('+', '-', '*', '/', '<', '>', '=', '<>'):
                exp.append({'=': '==', '<>': '!='}.get(token.value, token.value))
            else:
                raise AssertionError(token)
        tree = ast.parse(''.join(exp), mode='eval')
        class IfLazy(ast.NodeTransformer):
            def visit_Call(self, node):
                self.generic_visit(node)
                if isinstance(node.func, ast.Name) and node.func.id == 'IF':
                    return ast.copy_location(ast.IfExp(*node.args), node)
                return node
        tree = ast.fix_missing_locations(IfLazy().visit(tree))
        functions = {'REF': lambda ref: ler(aba, ref), 'SUM': soma, 'SUMIFS': sumifs,
                     'ROUND': lambda v, n: float(Decimal(str(v)).quantize(Decimal(10)**-n, rounding=ROUND_HALF_UP)),
                     'COUNT': lambda *v: sum(isinstance(x, (float, int)) for x in itens(v)),
                     'IF': lambda cond, sim, nao: sim if cond else nao}
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id not in functions:
                raise AssertionError(node.id)
            if not isinstance(node, (ast.Expression, ast.Call, ast.Name, ast.Load, ast.Constant,
                                     ast.BinOp, ast.UnaryOp, ast.Add, ast.Sub, ast.Mult, ast.Div,
                                     ast.USub, ast.UAdd, ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.Gt, ast.IfExp)):
                raise AssertionError(type(node))
        return eval(compile(tree, '<formula>', 'eval'), {'__builtins__': {}}, functions)
    return ler
