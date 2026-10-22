"""Copia semanal de lo que no se puede regenerar: lo aprendido, la configuración y los datos del programa.

Va a la carpeta `[copia]` de config.toml (y de ahí, con la sincronización, a las otras copias).
Las bases de datos se copian con el método seguro de SQLite, aunque el programa las tenga abiertas.
Se guardan las N últimas; las más antiguas van a la papelera.
"""
import datetime
import glob
import os
import sqlite3
import tempfile
import zipfile

from . import papelera
from .config import RAIZ

BASES = ['indice.sqlite', 'historial.sqlite', 'sincro.sqlite', 'docs.sqlite']


def hacer_copia(cfg, hoy: datetime.date | None = None) -> tuple[str, list[str]]:
    """Devuelve (ruta del zip, copias antiguas mandadas a la papelera)."""
    hoy = hoy or datetime.date.today()
    os.makedirs(cfg.carpeta_copia, exist_ok=True)
    destino = os.path.join(cfg.carpeta_copia, f'Organizador {hoy:%Y-%m-%d}.zip')
    with tempfile.TemporaryDirectory() as tmp:
        for base in BASES:
            origen = os.path.join(cfg.datos, base)
            if not os.path.exists(origen):
                continue
            src, dst = sqlite3.connect(origen), sqlite3.connect(os.path.join(tmp, base))
            try:
                src.backup(dst)
            finally:
                src.close()
                dst.close()
        parcial = destino + '.tmp'
        with zipfile.ZipFile(parcial, 'w', zipfile.ZIP_DEFLATED) as z:
            for base in BASES:
                if os.path.exists(os.path.join(tmp, base)):
                    z.write(os.path.join(tmp, base), f'datos/{base}')
            for nombre in ('aprendido.txt', 'config.toml'):
                ruta = cfg.aprendido if nombre == 'aprendido.txt' else cfg.archivo
                if os.path.exists(ruta):
                    z.write(ruta, nombre)
            z.writestr('LEEME.txt', f'Copia del Organizador del PC del {hoy:%d/%m/%Y}.\n'
                                    f'Para restaurarla: deja «datos/» dentro de la carpeta del programa ({RAIZ}) '
                                    'y aprendido.txt y config.toml junto a organizador.pyw (ver LEEME.md, '
                                    '«Cambiar de ordenador»).\n')
        os.replace(parcial, destino)
    viejas = sorted(glob.glob(os.path.join(cfg.carpeta_copia, 'Organizador ????-??-??.zip')))
    quitadas = []
    for v in viejas[:-cfg.copias_guardar] if cfg.copias_guardar > 0 else []:
        papelera.enviar(v)
        quitadas.append(v)
    return destino, quitadas
