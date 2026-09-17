# -*- coding: utf-8 -*-
import ast
p = r'C:\Users\雍远\.agents\skills\fire-check-consolidation\.rollback\SK-20260917-f3fix\f3_register.py.pre'
pre = open(p, encoding='utf-8').read()
tree = ast.parse(pre)
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and node.name == 'main':
        print('found main, body stmts =', len(node.body))
        for i, st in enumerate(node.body):
            if isinstance(st, ast.Assign):
                print(i, st.lineno, ast.unparse(st)[:90])
