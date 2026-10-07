"""The galleass model's geometry (constants and pure functions such as half_beam, z_top, gunport_y) without
Blender: galleass_model.py is parsed and only its imports, function definitions and plain assignments run.

    import model_geom; G = model_geom.load()      # dict of the model's globals
"""
import ast, os, sys, types

def load(path=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'galleass_model.py')):
    for m in ('bpy', 'bmesh'):
        sys.modules.setdefault(m, types.ModuleType(m))
    if 'mathutils' not in sys.modules:
        mu = types.ModuleType('mathutils'); mu.Vector = mu.Matrix = object; sys.modules['mathutils'] = mu
    g = {'__name__': 'model_geom'}
    for n in ast.parse(open(path, encoding='utf-8').read()).body:
        if isinstance(n, (ast.Assign, ast.AnnAssign)):
            src = ast.unparse(n)
            if 'argv' in src or 'bpy.' in src:
                continue
        elif not isinstance(n, (ast.FunctionDef, ast.Import, ast.ImportFrom, ast.ClassDef)):
            continue
        try:
            exec(compile(ast.Module([n], []), path, 'exec'), g)
        except Exception:
            pass      # assignments that need Blender objects
    return g
