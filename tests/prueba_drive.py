"""Prueba del sincronizador con Google Drive de verdad, en una carpeta de prueba.

    python tests/prueba_drive.py <carpeta local de trabajo>

Usa «G:\\Mi unidad\\_prueba_sincro» y «H:\\Mi unidad\\_prueba_sincro» (con archivos pequeños creados para la prueba)
y una carpeta local como si fuera OneDrive. No toca nada más de G: ni de H:.
Al final deja las dos carpetas de prueba en su sitio para comprobar la papelera; luego se mandan a la papelera.
"""
import os
import sys
import time
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from organizador import papelera
from organizador import sincro as S
from organizador.config import Config

LOCAL = os.path.abspath(sys.argv[1])
CARPETA = '_prueba_sincro'
O, G, H = os.path.join(LOCAL, 'OneDrive'), os.path.join(r'G:\Mi unidad', CARPETA), os.path.join(r'H:\Mi unidad', CARPETA)
resultados = []


def ok(cond, texto):
    resultados.append(bool(cond))
    print(('OK   ' if cond else 'FALLO') + ' ' + texto, flush=True)


def escribir(ruta, texto):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, 'w', encoding='utf-8') as f:
        f.write(texto)


def leer(ruta):
    with open(ruta, encoding='utf-8') as f:
        return f.read()


def esperar_drive(segundos=8):
    time.sleep(segundos)          # que Drive termine de procesar lo que acaba de cambiar


for d in (G, H):
    if os.path.exists(d):
        sys.exit(f'Ya existe {d}: no lo toco.')
for d in (O, G, H):
    os.makedirs(os.path.join(d, 'A'))
cfg = Config(descargas=os.path.join(LOCAL, 'D'), onedrive=O, universidad='A', carpetas_indice=['A'],
             datos=os.path.join(LOCAL, 'datos'), sincro_simulacion=False, max_borrados=20, minutos_repo=10,
             copias=[{'nombre': 'G:', 'raiz': G, 'carpetas': ['A']}, {'nombre': 'H:', 'raiz': H, 'carpetas': ['A']}])
os.makedirs(cfg.datos, exist_ok=True)
s = S.Sincronizador(cfg)
ok(*s.crear_estado_inicial())

# 1. Archivos nuevos en «OneDrive» → G: y H:
nfd = unicodedata.normalize('NFD', 'Pràctica àèíóú ñ.txt')
for nombre, texto in [('uno.txt', 'uno'), ('Tema 1 - Àlgebra.txt', 'àlgebra'), (nfd, 'nfd'),
                      (os.path.join('sub', 'dos.txt'), 'dos'), (os.path.join('sub', 'tres.txt'), 'tres')]:
    escribir(os.path.join(O, 'A', nombre), texto)
inf = s.pasada()
ok(inf.copiados['G:'] == 5 and inf.copiados['H:'] == 5, f'5 archivos nuevos copiados a G: y H: ({inf.resumen()})')
mt_o = os.path.getmtime(os.path.join(O, 'A', 'uno.txt'))
ok(abs(os.path.getmtime(os.path.join(G, 'A', 'uno.txt')) - mt_o) < 2, 'Drive conserva la fecha de modificación')
ok(os.path.exists(os.path.join(G, 'A', nfd)) or os.path.exists(os.path.join(G, 'A', unicodedata.normalize('NFC', nfd))),
   'el nombre con tildes (NFD) llega a G:')
esperar_drive()
inf = s.pasada()
ok(inf.resumen() == 'todo igual', f'la siguiente pasada no hace nada aunque Drive haya subido los archivos ({inf.resumen()})')

# 2. Renombrar en G: → se mueve en OneDrive y H:
os.rename(os.path.join(G, 'A', 'uno.txt'), os.path.join(G, 'A', 'Uno renombrado.txt'))
esperar_drive()
inf = s.pasada()
ok(inf.movidos['OneDrive'] == 1 and inf.movidos['H:'] == 1 and not inf.copiados,
   f'renombrar en G: se mueve en los demás, sin copiar ({inf.resumen()})')

# 3. Modificar en H: → OneDrive y G:
escribir(os.path.join(H, 'A', 'sub', 'dos.txt'), 'dos, corregido en H')
esperar_drive()
inf = s.pasada()
ok(leer(os.path.join(G, 'A', 'sub', 'dos.txt')) == 'dos, corregido en H', f'un cambio en H: llega a G: ({inf.resumen()})')

# 4. Renombrar una carpeta en OneDrive → una sola operación en G: y H:
os.rename(os.path.join(O, 'A', 'sub'), os.path.join(O, 'A', 'Subcarpeta'))
inf = s.pasada()
ok(inf.movidos['G:'] == 1 and inf.movidos['H:'] == 1 and os.path.isdir(os.path.join(G, 'A', 'Subcarpeta')),
   f'renombrar una carpeta es una sola operación en Drive ({inf.resumen()})')

# 5. Borrar en OneDrive → a la papelera en G: y H:
escribir(os.path.join(O, 'A', 'borrame-prueba-sincro.txt'), 'borrar')
s.pasada()
esperar_drive()
os.remove(os.path.join(O, 'A', 'borrame-prueba-sincro.txt'))
inf = s.pasada()
ok(len(inf.a_papelera) == 2 and all(papelera.buscar(p['ruta']) for p in inf.pasos),
   f'borrar en OneDrive manda el archivo a la papelera de G: y de H: ({inf.resumen()})')
esperar_drive()
inf = s.pasada()
ok(inf.resumen() == 'todo igual', f'todo igual al final ({inf.resumen()})')
s.db.close()
print(f'\n{sum(resultados)} de {len(resultados)} comprobaciones bien.')
