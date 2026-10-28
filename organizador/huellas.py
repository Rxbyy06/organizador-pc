"""Índice de huellas (hash) de las carpetas, para encontrar duplicados.

La primera pasada lee todos los archivos, así que solo trabaja con el PC inactivo y en
segundo plano. Después solo se vuelven a leer los archivos nuevos o cambiados.
"""
import hashlib
import logging
import os
import sqlite3
import threading
import time

from . import contenido
from .nombres import clave, ruta_larga
from .perfil import tokenizar

log = logging.getLogger(__name__)

IGNORAR_EXT = {'.tmp', '.crdownload', '.part', '.gdoc', '.gsheet', '.gslides', '.gform', '.gmap',
               '.gdraw', '.gsite', '.gjam', '.glink',
               '.orgsync-tmp', '.orgdocs-tmp'}          # copias a medias del propio programa
IGNORAR_NOMBRES = {'desktop.ini', 'thumbs.db', '.ds_store'}
# Archivos solo en la nube (OneDrive los descargaría al leerlos).
SOLO_EN_NUBE = 0x400000 | 0x40000 | 0x1000
CON_TEXTO = {'.pdf', '.docx', '.pptx'}
LOTE = 500                     # filas por escritura: entre lote y lote, los demás hilos pueden consultar


def ignorado(nombre: str) -> bool:
    n = nombre.lower()
    return n in IGNORAR_NOMBRES or n.startswith('~$') or os.path.splitext(n)[1] in IGNORAR_EXT


def huella(ruta: str) -> str:
    h = hashlib.blake2b(digest_size=20)
    with open(ruta_larga(ruta), 'rb') as f:
        while bloque := f.read(1 << 20):
            h.update(bloque)
    return h.hexdigest()


class Indice:
    def __init__(self, cfg):
        self.cfg = cfg
        self._lock = threading.RLock()
        self._ruta = os.path.join(cfg.datos, 'indice.sqlite')
        self.db = sqlite3.connect(self._ruta, check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS archivos (
                ruta TEXT PRIMARY KEY, nombre TEXT, tam INTEGER, mtime REAL,
                hash TEXT, texto_hash TEXT, palabras TEXT, hecho INTEGER DEFAULT 0,
                privado INTEGER DEFAULT 0);
            CREATE INDEX IF NOT EXISTS i_hash ON archivos(hash);
            CREATE INDEX IF NOT EXISTS i_texto ON archivos(texto_hash);
            CREATE INDEX IF NOT EXISTS i_tam ON archivos(tam);
            CREATE INDEX IF NOT EXISTS i_hecho ON archivos(hecho);
        ''')
        nc = os.path.normcase
        self._privado = [nc(p) for p in cfg.solo_huella]
        self._texto = [nc(p) for p in cfg.leer_texto_en]
        self._excluir = {nc(os.path.join(cfg.onedrive, p)) for p in cfg.excluir}
        self._contar()

    def _leer_todo(self, sql: str, args=()) -> list[tuple]:
        """Consulta larga con su propia conexión (WAL): no coge el candado ni hace esperar a nadie."""
        db = sqlite3.connect(self._ruta)
        try:
            return db.execute(sql, args).fetchall()
        finally:
            db.close()

    def _contar(self) -> None:
        self._progreso = tuple(self._leer_todo('SELECT COALESCE(SUM(hecho),0), COUNT(*) FROM archivos')[0])

    # ── Recorrido ───────────────────────────────────────────────────────────
    def _es(self, rel: str, prefijos: list[str]) -> bool:
        r = os.path.normcase(rel)
        return any(r == p or r.startswith(p + os.sep) for p in prefijos)

    def _recorrer(self):
        """(ruta relativa, tamaño, mtime) de los archivos locales de las carpetas del índice."""
        pila = [os.path.join(self.cfg.onedrive, c) for c in self.cfg.carpetas_indice]
        while pila:
            carpeta = pila.pop()
            try:
                with os.scandir(ruta_larga(carpeta)) as it:
                    entradas = list(it)
            except OSError:
                continue
            for e in entradas:
                ruta = os.path.join(carpeta, e.name)
                try:
                    if e.is_dir(follow_symlinks=False):
                        if e.name != '.git' and os.path.normcase(ruta) not in self._excluir:
                            pila.append(ruta)
                        continue
                    if ignorado(e.name):
                        continue
                    st = e.stat(follow_symlinks=False)
                except OSError:
                    continue
                rel = os.path.relpath(ruta, self.cfg.onedrive)
                yield rel, st.st_size, st.st_mtime, bool(st.st_file_attributes & SOLO_EN_NUBE)

    def escanear(self) -> tuple[int, int, int]:
        """Compara tamaño y fecha con lo guardado. Barato: no lee ningún archivo."""
        antes = {r: (t, m) for r, t, m in self._leer_todo('SELECT ruta, tam, mtime FROM archivos')}
        vistos, nuevos, cambiados = set(), [], []
        for rel, tam, mtime, en_nube in self._recorrer():
            vistos.add(rel)
            if en_nube:
                continue
            previo = antes.get(rel)
            if previo is None:
                nuevos.append((rel, tam, mtime))
            elif previo != (tam, mtime):
                cambiados.append((rel, tam, mtime))
        borrados = [r for r in antes if r not in vistos]
        cambios = nuevos + cambiados
        for i in range(0, len(cambios), LOTE):
            with self._lock, self.db:
                for rel, tam, mtime in cambios[i:i + LOTE]:
                    self._guardar_basico(rel, tam, mtime)
        for i in range(0, len(borrados), LOTE):
            with self._lock, self.db:
                self.db.executemany('DELETE FROM archivos WHERE ruta=?', [(r,) for r in borrados[i:i + LOTE]])
        self._contar()
        return len(nuevos), len(cambiados), len(borrados)

    def _guardar_basico(self, rel, tam, mtime, hash_=None):
        privado = self._es(rel, self._privado)
        palabras = None if privado else ' '.join(tokenizar(os.path.splitext(os.path.basename(rel))[0]))
        self.db.execute('''INSERT INTO archivos(ruta, nombre, tam, mtime, hash, texto_hash, palabras, hecho, privado)
                           VALUES (?,?,?,?,?,NULL,?,0,?)
                           ON CONFLICT(ruta) DO UPDATE SET nombre=excluded.nombre, tam=excluded.tam,
                             mtime=excluded.mtime, hash=excluded.hash, texto_hash=NULL,
                             palabras=excluded.palabras, hecho=0, privado=excluded.privado''',
                        (rel, clave(os.path.basename(rel)), tam, mtime, hash_, palabras, int(privado)))

    # ── Trabajo pesado (en segundo plano) ───────────────────────────────────
    def procesar(self, rel: str) -> None:
        ruta = os.path.join(self.cfg.onedrive, rel)
        try:
            st = os.stat(ruta_larga(ruta))
            if st.st_file_attributes & SOLO_EN_NUBE:
                return
            h = huella(ruta)
        except OSError:
            with self._lock, self.db:
                self.db.execute('DELETE FROM archivos WHERE ruta=?', (rel,))
            return
        texto_hash, palabras = None, None
        privado = self._es(rel, self._privado)
        if not privado and self._es(rel, self._texto) and os.path.splitext(rel)[1].lower() in CON_TEXTO:
            c = contenido.analizar(ruta, completo=True)
            texto_hash = c.texto_hash
            palabras = ' '.join(tokenizar(f'{os.path.splitext(os.path.basename(rel))[0]} {c.titulo} {c.texto[:6000]}', 300))
        with self._lock, self.db:
            self.db.execute('UPDATE archivos SET hash=?, texto_hash=?, palabras=COALESCE(?, palabras), hecho=1, '
                            'tam=?, mtime=? WHERE ruta=?', (h, texto_hash, palabras, st.st_size, st.st_mtime, rel))

    def trabajar(self, puede_seguir, pausa: float = 0.002) -> int:
        """Procesa pendientes mientras puede_seguir() sea cierto. Devuelve cuántos ha hecho."""
        hechos = 0
        try:
            while puede_seguir():
                with self._lock:
                    filas = [r for (r,) in self.db.execute('SELECT ruta FROM archivos WHERE hecho=0 LIMIT 50')]
                if not filas:
                    break
                for rel in filas:
                    if not puede_seguir():
                        return hechos
                    try:
                        self.procesar(rel)
                    except Exception:
                        log.exception('No pude indexar %s', rel)
                        with self._lock, self.db:
                            self.db.execute('UPDATE archivos SET hecho=1 WHERE ruta=?', (rel,))
                    hechos += 1
                    time.sleep(pausa)
                self._contar()
            return hechos
        finally:
            if hechos:
                self._contar()

    # ── Consultas ───────────────────────────────────────────────────────────
    def progreso(self) -> tuple[int, int]:
        """(con huella, total). Lo último que se contó: no espera a nadie (lo lee el icono)."""
        return self._progreso

    def iguales(self, hash_: str, tam: int) -> list[str]:
        """Archivos idénticos (por huella). Si alguno del mismo tamaño aún no tiene huella, la calcula ya."""
        with self._lock:
            sin_huella = [r for (r,) in self.db.execute(
                'SELECT ruta FROM archivos WHERE tam=? AND hash IS NULL', (tam,))]
        for rel in sin_huella:
            try:
                h = huella(os.path.join(self.cfg.onedrive, rel))
            except OSError:
                continue
            with self._lock, self.db:
                self.db.execute('UPDATE archivos SET hash=? WHERE ruta=?', (h, rel))
        with self._lock:
            return [os.path.join(self.cfg.onedrive, r) for (r,) in
                    self.db.execute('SELECT ruta FROM archivos WHERE hash=? AND tam=?', (hash_, tam))]

    def mismo_texto(self, texto_hash: str | None, hash_: str) -> list[str]:
        if not texto_hash:
            return []
        with self._lock:
            return [os.path.join(self.cfg.onedrive, r) for (r,) in self.db.execute(
                'SELECT ruta FROM archivos WHERE texto_hash=? AND hash<>?', (texto_hash, hash_))]

    def huella_de(self, rel: str, tam: int, mtime: float) -> str | None:
        """La huella ya calculada de un archivo, si no ha cambiado desde entonces."""
        with self._lock:
            f = self.db.execute('SELECT hash FROM archivos WHERE ruta=? AND tam=? AND abs(mtime-?)<1 AND hash IS NOT NULL',
                                (rel, tam, mtime)).fetchone()
        return f[0] if f else None

    def filas_perfil(self):
        return self._leer_todo('SELECT ruta, palabras, mtime FROM archivos WHERE privado=0')

    # ── Cambios hechos por el programa ──────────────────────────────────────
    def anadir(self, ruta: str, hash_: str | None = None) -> None:
        rel = self.cfg.relativa(ruta)
        if os.path.isabs(rel) or not self._es(rel, [os.path.normcase(c) for c in self.cfg.carpetas_indice]):
            return
        try:
            st = os.stat(ruta_larga(ruta))
        except OSError:
            return
        with self._lock, self.db:
            self._guardar_basico(rel, st.st_size, st.st_mtime, hash_)

    def quitar(self, ruta: str) -> None:
        rel = self.cfg.relativa(ruta)
        with self._lock, self.db:
            pre = rel + os.sep
            self.db.execute('DELETE FROM archivos WHERE ruta=? OR substr(ruta, 1, ?)=?', (rel, len(pre), pre))
