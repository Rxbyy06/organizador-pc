"""Herramientas de línea de comandos (para pruebas y mantenimiento).

    python -m organizador.herramientas indexar     ← índice completo ya, sin esperar a que el PC esté inactivo
    python -m organizador.herramientas aprender    ← vuelve a crear aprendido.txt desde lo ya ordenado
    python -m organizador.herramientas evaluar     ← mide cuánto acierta la asignatura
    python -m organizador.herramientas sugerir <archivo>
    python -m organizador.herramientas sincro-inicial ← estado inicial del sincronizador (si los tres sitios son iguales)
    python -m organizador.herramientas sincro [--de-verdad] ← una pasada (por defecto, en simulación)
Todas aceptan --config <archivo.toml>.
"""
import argparse
import os
import random
import sys
import time

from . import aprendizaje, config, sistema
from .huellas import Indice
from .perfil import Perfil, clase_de, tokenizar


def _cpu() -> float:
    import ctypes
    from ctypes import wintypes
    c, e, k, u = (wintypes.FILETIME() for _ in range(4))
    ctypes.windll.kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    ctypes.windll.kernel32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.c_void_p] * 4
    ctypes.windll.kernel32.GetProcessTimes(ctypes.windll.kernel32.GetCurrentProcess(),
                                           ctypes.byref(c), ctypes.byref(e), ctypes.byref(k), ctypes.byref(u))
    return ((k.dwHighDateTime << 32 | k.dwLowDateTime) + (u.dwHighDateTime << 32 | u.dwLowDateTime)) / 1e7


def indexar(cfg) -> None:
    ind = Indice(cfg)
    t0, c0 = time.time(), _cpu()
    print('Escaneo (nuevos, cambiados, borrados):', ind.escanear(), f'{time.time() - t0:.1f} s')
    sistema.hilo_en_segundo_plano()
    t1, ultimo = time.time(), time.time()

    def seguir():
        nonlocal ultimo
        if time.time() - ultimo > 15:
            print('  progreso', ind.progreso(), flush=True)
            ultimo = time.time()
        return True
    n = ind.trabajar(seguir, pausa=0)
    dur = time.time() - t1
    print(f'Procesados {n} archivos en {dur:.0f} s; CPU usada {_cpu() - c0:.0f} s '
          f'(≈{100 * (_cpu() - c0) / max(dur, 1) / os.cpu_count():.1f} % del total de {os.cpu_count()} núcleos)')


def evaluar(cfg, n: int = 300) -> None:
    ind = Indice(cfg)
    filas = ind.filas_perfil()
    uni = [f for f in filas if f[0].startswith(cfg.universidad + os.sep) and clase_de(f[0])[0] != cfg.universidad
           and f[0].lower().endswith('.pdf') and f[1]]
    random.seed(1)
    prueba = set(r for r, _, _ in random.sample(uni, min(n, len(uni))))
    p = Perfil()
    p.construir([f for f in filas if f[0] not in prueba])
    aciertos = seguros = aciertos_seguros = 0
    for rel, palabras, _ in (f for f in filas if f[0] in prueba):
        real = clase_de(rel)[0]
        toks = tokenizar(f'{os.path.splitext(os.path.basename(rel))[0]} {palabras}')
        r = p.clasificar(toks, cfg.universidad)
        if not r:
            continue
        ok = r[0][0] == real
        aciertos += ok
        seguro = r[0][1] >= 0.12 and r[0][1] >= (r[1][1] if len(r) > 1 else 0) * 1.25
        seguros += seguro
        aciertos_seguros += ok and seguro
    print(f'Asignatura acertada: {aciertos}/{len(prueba)} ({100 * aciertos / len(prueba):.0f} %). '
          f'Marcadas «seguro»: {seguros}, de ellas acertadas {aciertos_seguros}.')


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('orden', choices=['indexar', 'aprender', 'evaluar', 'sugerir', 'sincro-inicial', 'sincro'])
    ap.add_argument('archivo', nargs='?')
    ap.add_argument('--config')
    ap.add_argument('--de-verdad', action='store_true')
    a = ap.parse_args()
    cfg = config.cargar(a.config)
    if a.orden == 'indexar':
        indexar(cfg)
    elif a.orden == 'aprender':
        n = aprendizaje.crear_inicial(cfg.aprendido, cfg.onedrive, cfg.carpetas_indice, cfg.ruta_uni,
                                      cfg.webs_genericas, cfg.solo_huella + cfg.excluir)
        print(f'{n} reglas escritas en {cfg.aprendido}')
    elif a.orden == 'evaluar':
        evaluar(cfg)
    elif a.orden in ('sincro-inicial', 'sincro'):
        from .sincro import Sincronizador
        s = Sincronizador(cfg, None, Indice(cfg))
        t0, c0 = time.time(), _cpu()
        if a.orden == 'sincro-inicial':
            print(*s.crear_estado_inicial())
        else:
            inf = s.pasada(simulacion=not a.de_verdad)
            print(('SIMULACIÓN: ' if inf.simulacion else '') + inf.resumen())
            for linea in (inf.plan + inf.errores + inf.avisos + inf.repos_ocupados)[:200]:
                print('  ', linea)
            if inf.error:
                print('ERROR:', inf.error)
        print(f'{time.time() - t0:.0f} s; CPU {_cpu() - c0:.1f} s')
    elif a.orden == 'sugerir':
        from .sugeridor import Sugeridor
        ind = Indice(cfg)
        p = Perfil()
        p.construir(ind.filas_perfil())
        sug = Sugeridor(cfg, aprendizaje.Aprendido(cfg.aprendido, cfg.onedrive, True), ind, p)
        s = sug.sugerir(a.archivo)
        print('Carpeta:', cfg.relativa(s.carpeta), '\nNombre :', s.nombre + s.ext, '\nMotivo :', s.motivo,
              '\nSeguro :', s.seguro)
        for av in sug.avisos(s, s.carpeta, s.nombre, True):
            print('Aviso  :', av.texto)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
