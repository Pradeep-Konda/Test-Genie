import ast
import os

def parse_routes(codebase_path):
    routes = []
    for root, _, files in os.walk(codebase_path):
        for file in files:
            if file.endswith(".py"):
                with open(os.path.join(root, file), "r") as f:
                    tree = ast.parse(f.read())
                    for node in ast.walk(tree):
                        if isinstance(node, ast.FunctionDef):
                            for decorator in node.decorator_list:
                                if isinstance(decorator, ast.Call) and hasattr(decorator.func, 'attr'):
                                    if decorator.func.attr == 'route':
                                        route = decorator.args[0].s
                                        method = 'GET'  # Simplification
                                        routes.append({
                                            "path": route,
                                            "method": method,
                                            "function": node.name,
                                            "summary": ast.get_docstring(node) or ""
                                        })
    return routes
