"""Lo que el programa hace en disco, siempre con su «Deshacer»; y el historial de 30 días.

Cada acción es una lista de pasos. Si un paso falla, se deshacen los anteriores.
En modo simulación no se ejecuta ningún paso: solo se anota lo que se habría hecho.
"""
import json
import logging
import os
import shutil
import sqlite3
import threading
import time
import zlib

from . import carpetas as C
from . import papelera, zips
from .nombres import clave, ruta_larga

log = logging.getLogger(__name__)


class Historial:
    def __init__(self, cfg):
        self.cfg = cfg
        self._lock = threading.RLock()
        self.db = sqlite3.connect(os.path.join(cfg.datos, 'historial.sqlite'), check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS acciones (
                id INTEGER PRIMARY KEY, fecha REAL, tipo TEXT, descripcion TEXT, pasos TEXT, estado TEXT);
            CREATE TABLE IF NOT EXISTS descargas (
                nombre TEXT PRIMARY KEY, primera_vez REAL, presentado INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS estado (clave TEXT PRIMARY KEY, valor REAL);
            CREATE TABLE IF NOT EXISTS stats (fecha REAL, tipo TEXT, datos TEXT);
            CREATE TABLE IF NOT EXISTS duplicados (hash TEXT PRIMARY KEY, estado TEXT);
            CREATE TABLE IF NOT EXISTS dejadas (ruta TEXT PRIMARY KEY, desde REAL);
        ''')
        columnas = [c[1] for c in self.db.execute('PRAGMA table_info(descargas)')]
        if 'aviso' not in columnas:                     # bases antiguas: cuándo se avisó de que se iba a la Papelera
            self.db.execute('ALTER TABLE descargas ADD COLUMN aviso REAL')

    def registrar(self, tipo: str, descripcion: str, pasos: list, estado: str) -> int:
        with self._lock, self.db:
            return self.db.execute('INSERT INTO acciones(fecha, tipo, descripcion, pasos, estado) VALUES (?,?,?,?,?)',
                                   (time.time(), tipo, descripcion, json.dumps(pasos, ensure_ascii=False), estado)
                                   ).lastrowid

    def marcar(self, id_: int, estado: str) -> None:
        with self._lock, self.db:
            self.db.execute('UPDATE acciones SET estado=? WHERE id=?', (estado, id_))

    def lista(self) -> list[tuple]:
        desde = time.time() - self.cfg.dias_historial * 86400
        with self._lock:
            return self.db.execute('SELECT id, fecha, tipo, descripcion, estado FROM acciones WHERE fecha>=? '
                                   'ORDER BY id DESC', (desde,)).fetchall()

    def pasos(self, id_: int) -> tuple[list, str]:
        with self._lock:
            p, e = self.db.execute('SELECT pasos, estado FROM acciones WHERE id=?', (id_,)).fetchone()
        return json.loads(p), e

    def podar(self) -> None:
        with self._lock, self.db:
            self.db.execute('DELETE FROM acciones WHERE fecha<?', (time.time() - self.cfg.dias_historial * 86400,))

    # Estado de Descargas: qué archivos ya se le han enseñado al usuario.
    def descarga_vista(self, nombre: str) -> tuple[float, bool] | None:
        with self._lock:
            f = self.db.execute('SELECT primera_vez, presentado FROM descargas WHERE nombre=?', (clave(nombre),)).fetchone()
        return (f[0], bool(f[1])) if f else None

    def descarga_nueva(self, nombre: str, presentado: bool = False, cuando: float | None = None) -> None:
        with self._lock, self.db:
            self.db.execute('INSERT INTO descargas(nombre, primera_vez, presentado) VALUES (?,?,?) '
                            'ON CONFLICT(nombre) DO UPDATE SET presentado=MAX(presentado, excluded.presentado)',
                            (clave(nombre), cuando or time.time(), int(presentado)))

    def descarga_fuera(self, nombre: str) -> None:
        with self._lock, self.db:
            self.db.execute('DELETE FROM descargas WHERE nombre=?', (clave(nombre),))

    def descarga_info(self, nombre: str) -> tuple[float, float | None] | None:
        """(primera vez, cuándo se avisó) de algo de Descargas."""
        with self._lock:
            return self.db.execute('SELECT primera_vez, aviso FROM descargas WHERE nombre=?', (clave(nombre),)).fetchone()

    def descarga_avisada(self, nombre: str, cuando: float) -> None:
        with self._lock, self.db:
            self.db.execute('UPDATE descargas SET aviso=? WHERE nombre=?', (cuando, clave(nombre)))

    def leer_estado(self, k: str, defecto: float = 0.0) -> float:
        with self._lock:
            f = self.db.execute('SELECT valor FROM estado WHERE clave=?', (k,)).fetchone()
        return f[0] if f else defecto

    def poner_estado(self, k: str, v: float) -> None:
        with self._lock, self.db:
            self.db.execute('INSERT INTO estado VALUES (?,?) ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor', (k, v))

    def dejada_desde(self, ruta: str) -> float | None:
        """Cuándo se marcó «Dejar» por primera vez (None si nunca)."""
        with self._lock:
            f = self.db.execute('SELECT desde FROM dejadas WHERE ruta=?', (os.path.normcase(ruta),)).fetchone()
        return f[0] if f else None

    def dejar(self, ruta: str, cuando: float) -> None:
        with self._lock, self.db:          # se queda la primera vez: de ahí cuenta el mes
            self.db.execute('INSERT OR IGNORE INTO dejadas VALUES (?,?)', (os.path.normcase(ruta), cuando))

    # Números de cada pasada (para el resumen semanal) y duplicados ya enseñados.
    def apuntar(self, tipo: str, datos: dict, fecha: float | None = None) -> None:
        with self._lock, self.db:
            self.db.execute('INSERT INTO stats VALUES (?,?,?)', (fecha or time.time(), tipo,
                                                                 json.dumps(datos, ensure_ascii=False)))
            self.db.execute('DELETE FROM stats WHERE fecha<?', (time.time() - 60 * 86400,))

    def stats_desde(self, desde: float) -> list[tuple[float, str, dict]]:
        with self._lock:
            filas = self.db.execute('SELECT fecha, tipo, datos FROM stats WHERE fecha>=? ORDER BY fecha', (desde,)).fetchall()
        return [(f, t, json.loads(d)) for f, t, d in filas]

    def acciones_desde(self, desde: float) -> list[tuple]:
        with self._lock:
            return self.db.execute('SELECT tipo, estado, descripcion FROM acciones WHERE fecha>=?', (desde,)).fetchall()

    def duplicados_vistos(self) -> dict[str, str]:
        with self._lock:
            return dict(self.db.execute('SELECT hash, estado FROM duplicados'))

    def marcar_duplicados(self, hashes, estado: str) -> None:
        with self._lock, self.db:
            self.db.executemany('INSERT OR REPLACE INTO duplicados VALUES (?,?)', [(h, estado) for h in hashes])

    def descargas_sincronizar(self, presentes: list[str]) -> None:
        claves = {clave(n) for n in presentes}
        with self._lock, self.db:
            for (n,) in self.db.execute('SELECT nombre FROM descargas').fetchall():
                if n not in claves:
                    self.db.execute('DELETE FROM descargas WHERE nombre=?', (n,))


class Ejecutor:
    def __init__(self, cfg, historial: Historial, indice, aprendido):
        self.cfg, self.historial, self.indice, self.aprendido = cfg, historial, indice, aprendido
        self._lock = threading.Lock()

    # ── Pasos ───────────────────────────────────────────────────────────────
    def _hacer(self, paso: dict) -> None:
        op = paso['op']
        if op == 'crear_carpeta':
            os.makedirs(ruta_larga(paso['ruta']))
        elif op == 'mover':
            if os.path.exists(ruta_larga(paso['a'])):
                raise FileExistsError(f'ya existe {paso["a"]}')
            shutil.move(ruta_larga(paso['de']), ruta_larga(paso['a']))
            self.indice.quitar(paso['de'])
            self.indice.anadir(paso['a'], paso.get('hash'))
        elif op == 'papelera':
            paso['fecha'] = papelera.enviar(paso['ruta'])
            self.indice.quitar(paso['ruta'])
        elif op == 'extraer':
            hechos = paso.setdefault('archivos', [])
            creadas = paso.setdefault('carpetas', [])
            for info, destino in self._planear_zip(paso):
                if destino is None:
                    continue
                creadas += [c for c in _carpetas_que_faltan(os.path.dirname(destino)) if c not in creadas]
                zips.extraer(paso['zip'], info, destino)
                hechos.append(destino)
                self.indice.anadir(destino)

    def _planear_zip(self, paso: dict):
        """(entrada, destino) para cada archivo; destino None si ya existe idéntico."""
        z = zips.analizar(paso['zip'])
        usados = set()
        for info, destino in zips.destinos(z, paso['carpeta'], paso['nombre']):
            if os.path.exists(ruta_larga(destino)):
                try:
                    if os.path.getsize(ruta_larga(destino)) == info.file_size and _crc(destino) == info.CRC:
                        yield info, None
                        continue
                except OSError:
                    pass
                base, ext = os.path.splitext(destino)
                n = 2
                while os.path.exists(ruta_larga(f'{base} ({n}){ext}')) or clave(f'{base} ({n}){ext}') in usados:
                    n += 1
                destino = f'{base} ({n}){ext}'
            usados.add(clave(destino))
            yield info, destino

    def _deshacer_paso(self, paso: dict) -> None:
        op = paso['op']
        if op == 'crear_carpeta':
            try:
                os.rmdir(ruta_larga(paso['ruta']))
            except OSError:
                pass                    # no está vacía: se queda
        elif op == 'mover':
            if not os.path.exists(ruta_larga(paso['a'])):
                raise FileNotFoundError(f'«{os.path.basename(paso["a"])}» ya no está donde lo dejé')
            destino = paso['de']
            if os.path.exists(ruta_larga(destino)):
                base, ext = os.path.splitext(destino)
                destino = f'{base} (deshecho){ext}'
            if os.path.dirname(destino) == os.path.normpath(self.cfg.descargas):
                self.historial.descarga_nueva(os.path.basename(destino), presentado=True)
            shutil.move(ruta_larga(paso['a']), ruta_larga(destino))
            self.indice.quitar(paso['a'])
        elif op == 'papelera':
            if os.path.dirname(paso['ruta']) == os.path.normpath(self.cfg.descargas):
                self.historial.descarga_nueva(os.path.basename(paso['ruta']), presentado=True)
            restaurado = papelera.restaurar(paso['ruta'], paso.get('fecha', 0))
            self.indice.anadir(restaurado)
        elif op == 'extraer':
            for ruta in reversed(paso.get('archivos', [])):
                if os.path.exists(ruta_larga(ruta)):
                    papelera.enviar(ruta)
                    self.indice.quitar(ruta)
            for carpeta in sorted(paso.get('carpetas', []), key=len, reverse=True):
                try:
                    os.rmdir(ruta_larga(carpeta))
                except OSError:
                    pass

    def _ejecutar(self, tipo: str, descripcion: str, pasos: list[dict]) -> str:
        with self._lock:
            if self.cfg.simulacion:
                self.historial.registrar(tipo, '[Simulación] ' + descripcion, pasos, 'simulado')
                log.info('[simulación] %s: %s', descripcion, pasos)
                return '[Simulación] ' + descripcion
            hechos = []
            try:
                for paso in pasos:
                    self._hacer(paso)
                    hechos.append(paso)
            except Exception as e:
                log.exception('Falló «%s»; deshago lo hecho', descripcion)
                for paso in reversed(hechos):
                    try:
                        self._deshacer_paso(paso)
                    except Exception:
                        log.exception('No pude deshacer %s', paso)
                self.historial.registrar(tipo, f'{descripcion} — NO SE HIZO: {e}', hechos, 'error')
                raise
            self.historial.registrar(tipo, descripcion, pasos, 'hecho')
            log.info('%s', descripcion)
            return descripcion

    # ── Acciones ────────────────────────────────────────────────────────────
    def aceptar(self, s, carpeta: str, nombre: str, *, descomprimir: bool, quitar: list[str],
                ext: str) -> str:
        """Lleva la descarga a carpeta/nombre. «quitar»: archivos viejos que van a la Papelera."""
        pasos = [{'op': 'crear_carpeta', 'ruta': r} for r in _carpetas_que_faltan(carpeta)]
        pasos += [{'op': 'papelera', 'ruta': r} for r in quitar]
        rel = self.cfg.relativa(carpeta)
        if s.es_zip and descomprimir:
            pasos.append({'op': 'extraer', 'zip': s.archivo, 'carpeta': carpeta, 'nombre': nombre})
            pasos.append({'op': 'papelera', 'ruta': s.archivo})
            que = f'«{nombre}{ext}»' if s.zip.archivo_unico else f'{s.zip.total} archivos en «{nombre}»'
            descripcion = f'Descomprimido «{os.path.basename(s.archivo)}» → {que} ({rel}); el zip, a la Papelera'
        else:
            pasos.append({'op': 'mover', 'de': s.archivo, 'a': os.path.join(carpeta, nombre + ext), 'hash': s.hash})
            descripcion = f'Movido «{os.path.basename(s.archivo)}» → {rel}\\{nombre}{ext}'
        if quitar:
            descripcion += f' (y {len(quitar)} antiguo{"s" if len(quitar) > 1 else ""} a la Papelera)'
        res = self._ejecutar('mover', descripcion, pasos)
        self._aprender(s, carpeta)
        return res

    def descartar(self, s) -> str:
        return self._ejecutar('descartar', f'Descartado «{os.path.basename(s.archivo)}» (a la Papelera)',
                              [{'op': 'papelera', 'ruta': s.archivo}])

    def limpiar_descargas(self, rutas: list[str]) -> str:
        nombres = ', '.join(f'«{os.path.basename(r)}»' for r in rutas[:4]) + (' y más' if len(rutas) > 4 else '')
        return self._ejecutar('limpieza', f'Limpieza de Descargas ({self.cfg.dias_descargas:g} días): '
                                          f'{len(rutas)} a la Papelera — {nombres}',
                              [{'op': 'papelera', 'ruta': r} for r in rutas])

    def tirar(self, ruta: str, motivo: str) -> str:
        return self._ejecutar('papelera', f'«{self.cfg.relativa(ruta)}» a la Papelera ({motivo})',
                              [{'op': 'papelera', 'ruta': ruta}])

    def revisar_capturas(self, borrar: list[str], guardar: list[tuple[str, str, str]]) -> str:
        """guardar: (ruta, carpeta destino, nombre con extensión)."""
        pasos = [{'op': 'papelera', 'ruta': r} for r in borrar]
        for ruta, carpeta, nombre in guardar:
            pasos += [{'op': 'crear_carpeta', 'ruta': c} for c in _carpetas_que_faltan(carpeta)
                      if not any(p.get('ruta') == c for p in pasos)]
            pasos.append({'op': 'mover', 'de': ruta, 'a': os.path.join(carpeta, nombre)})
        partes = [f'{len(borrar)} a la Papelera'] if borrar else []
        partes += [f'«{n}» guardada en {self.cfg.relativa(c)}' for _, c, n in guardar]
        return self._ejecutar('revision', 'Revisión semanal de capturas: ' + '; '.join(partes), pasos)

    def deshacer(self, id_: int) -> str:
        pasos, estado = self.historial.pasos(id_)
        if estado != 'hecho':
            raise ValueError('esta acción no se puede deshacer')
        with self._lock:
            for paso in reversed(pasos):
                self._deshacer_paso(paso)
            self.historial.marcar(id_, 'deshecho')
        return 'Deshecho'

    def _aprender(self, s, carpeta: str) -> None:
        asig = C.asignatura_de(carpeta, self.cfg.ruta_uni)
        dest = self.cfg.relativa(carpeta)
        dest_asig = self.cfg.relativa(asig.ruta) if asig else dest
        reglas = {}
        for tipo, valor in s.origen.claves():
            if tipo == 'web' and valor in self.cfg.webs_genericas:
                continue
            general = tipo == 'curso' or (tipo == 'contexto' and s.origen.componente == 'course')
            reglas[(tipo, valor)] = dest_asig if general else dest
        try:
            self.aprendido.aprender(reglas)
        except OSError:
            log.exception('No pude guardar lo aprendido')


def _crc(ruta: str) -> int:
    crc = 0
    with open(ruta_larga(ruta), 'rb') as f:
        while bloque := f.read(1 << 20):
            crc = zlib.crc32(bloque, crc)
    return crc


def _carpetas_que_faltan(carpeta: str) -> list[str]:
    faltan = []
    while carpeta and not os.path.isdir(ruta_larga(carpeta)):
        faltan.append(carpeta)
        carpeta = os.path.dirname(carpeta)
    return list(reversed(faltan))
