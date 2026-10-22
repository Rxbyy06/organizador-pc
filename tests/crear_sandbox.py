"""Crea una carpeta de pruebas que imita OneDrive y Descargas, sin tocar nada real.

    python tests/crear_sandbox.py <carpeta de pruebas>

- OneDrive: las mismas carpetas que el de verdad, con archivos de relleno del mismo nombre
  (su contenido es solo su ruta). La carpeta privada de notas no se copia.
- Unos pocos PDF reales copiados, para probar duplicados y versiones.
- config.toml de pruebas (sin simulación) y una copia de aprendido.txt.
Las descargas de prueba las añaden prueba_organizador.py y prueba_limpieza_revision.py.
"""
import os
import re
import shutil
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from organizador import config  # noqa: E402
from organizador.nombres import ruta_larga as L  # noqa: E402

UNI = '1 - Universidad UPF'
COPIAR_REALES = [   # (ruta real relativa) → se copia tal cual al mismo sitio
    rf'{UNI}\1r - T2 - Càlcul II\5 - Exámenes\2023-24 - Parcial - Soluciones.pdf',
]


def crear(destino: str) -> None:
    cfg = config.cargar()
    REAL = cfg.onedrive
    if os.path.exists(destino):
        shutil.rmtree('\\\\?\\' + destino)       # con prefijo: dentro hay rutas de más de 260
    od = os.path.join(destino, 'OneDrive')
    privadas = {os.path.normcase(os.path.join(REAL, p)) for p in cfg.solo_huella}
    n = 0
    for carpeta in cfg.carpetas_indice:
        for raiz, dirs, archivos in os.walk(os.path.join(REAL, carpeta)):
            dirs[:] = [d for d in dirs if d != '.git' and os.path.normcase(os.path.join(raiz, d)) not in privadas]
            rel = os.path.relpath(raiz, REAL)
            os.makedirs(L(os.path.join(od, rel)), exist_ok=True)
            for a in archivos:
                if a.lower() == 'desktop.ini':
                    continue
                with open(L(os.path.join(od, rel, a)), 'w', encoding='utf-8') as f:
                    f.write(f'relleno: {rel}\\{a}\n')
                n += 1
    for rel in COPIAR_REALES:
        if os.path.exists(os.path.join(REAL, rel)):
            shutil.copy2(os.path.join(REAL, rel), os.path.join(od, rel))
    os.makedirs(os.path.join(destino, 'Downloads'))
    for c in ('Capturas de pantalla', 'Captures'):
        os.makedirs(os.path.join(destino, c))
    aprendido = os.path.join(RAIZ, 'aprendido.txt')
    if not os.path.exists(aprendido):
        aprendido = os.path.join(RAIZ, 'aprendido.example.txt')
    shutil.copy2(aprendido, os.path.join(destino, 'aprendido.txt'))
    with open(cfg.archivo, encoding='utf-8') as f:
        texto = f.read()
    texto = re.sub(r"(?m)^descargas = '.*'$", lambda m: f"descargas = '{os.path.join(destino, 'Downloads')}'", texto)
    texto = re.sub(r"(?m)^onedrive = '.*'$", lambda m: f"onedrive = '{od}'", texto)
    texto = texto.replace('minutos_inactivo = 5', 'minutos_inactivo = 0')
    texto = re.sub(r'(?m)^(\[organizador\][^\[]*?)simulacion = true', r'\1simulacion = false', texto)
    # El sincronizador de pruebas nunca puede apuntar a los G: y H: de verdad.
    texto = re.sub(r"(?m)^raiz = '([GH]):\\Mi unidad'$",
                   lambda m: f"raiz = '{destino}\\{m.group(1)}_no_existe'", texto)
    texto = re.sub(r"(?m)^exportados = '([GH]):\\Mi unidad\\_exportados_docs'$",
                   lambda m: f"exportados = '{destino}\\{m.group(1)}_no_existe\\_exportados_docs'", texto)
    assert r"G:\Mi unidad" not in texto and r"H:\Mi unidad" not in texto
    texto = re.sub(r"(?m)^carpetas = \['C:\\Users\\[^\\]+\\OneDrive\\Im.*$",
                   lambda m: f"carpetas = ['{destino}\\Capturas de pantalla', '{destino}\\Captures']", texto)
    texto += "\n[programa]\ndatos = 'datos'\naprendido = 'aprendido.txt'\n"
    with open(os.path.join(destino, 'config.toml'), 'w', encoding='utf-8') as f:
        f.write(texto)
    print(f'Carpeta de pruebas lista en {destino}: {n} archivos de relleno')


if __name__ == '__main__':
    crear(os.path.abspath(sys.argv[1]))
