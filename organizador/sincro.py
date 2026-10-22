"""Sincronizador en estrella: OneDrive en el centro; G: (solo la uni) y H: (todas las carpetas principales).

Cada pasada:
  1. Escanea los sitios disponibles (solo tamaño y fecha) y los compara con el estado de la última
     sincronización de ese mismo sitio. Solo calcula la huella de lo que ha cambiado.
  2. Decide, archivo a archivo, cómo debe quedar («objetivo»): lo cambiado en un sitio gana; si cambió
     en dos sitios de forma distinta es un conflicto y se guardan las dos versiones.
  3. Hace que cada sitio quede como el objetivo: primero OneDrive (recoger), luego G: y H: (repartir).
     Lo que desaparece y reaparece con otro nombre se mueve, no se copia y borra.
  4. Guarda el nuevo estado.

Seguridad: un sitio que no responde se salta entero (nunca cuenta como «se ha borrado todo»);
si una pasada fuera a mandar a la papelera más de N archivos, se para y pregunta; nada se borra
definitivamente (va a la papelera de ese sitio); los repos git solo van de OneDrive a las copias,
y solo cuando llevan unos minutos sin cambios.
"""
import datetime
import logging
import os
import random
import shutil
import sqlite3
import stat
import threading
import time
from collections import Counter
from dataclasses import dataclass, field

from . import papelera
from .huellas import huella, ignorado
from .nombres import nfc, partir_ext, ruta_larga

log = logging.getLogger(__name__)
SEP = os.sep
DIR = 'DIR'
TMP = '.orgsync-tmp'
EXCLUIR_DIRS = {'$recycle.bin', '_exportados_docs', 'system volume information', '.tmp.drivedownload',
                '.tmp.driveupload'}
MARGEN_ESPACIO = 50 << 20


def clave(rel: str) -> str:
    return nfc(rel).casefold()


def excluido(nombre: str) -> bool:
    n = nombre.lower()
    return ignorado(nombre) or n.endswith(TMP) or n.startswith('.~lock.')


@dataclass
class Entrada:
    ruta: str              # relativa a la raíz del sitio, tal cual se llama allí
    tam: int = 0
    mtime: float = 0.0
    hash: str | None = None
    dir: bool = False


@dataclass
class Objetivo:
    hash: str | None       # None = no debe existir; DIR = carpeta
    ruta: str
    fuente: str | None = None     # sitio que tiene ese contenido
    origen: str | None = None     # en conflictos: ruta (en «fuente») de la versión que se aparta


@dataclass
class Replica:
    nombre: str
    raiz: str
    carpetas: list[str]

    def __post_init__(self):
        self._tops = {clave(c) for c in self.carpetas}
        self.excluidas: set[str] = set()      # p. ej. los Word de los Docs de esta cuenta: nunca van aquí

    def cubre(self, k: str) -> bool:
        return k.split(SEP, 1)[0] in self._tops and k not in self.excluidas

    def ruta(self, rel: str) -> str:
        return os.path.join(self.raiz, rel)


@dataclass
class Informe:
    simulacion: bool = False
    plan: list[str] = field(default_factory=list)
    copiados: Counter = field(default_factory=Counter)
    movidos: Counter = field(default_factory=Counter)
    a_papelera: list[str] = field(default_factory=list)
    conflictos: list[str] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)
    sin_espacio: Counter = field(default_factory=Counter)
    retenidos: list[tuple[str, list[str]]] = field(default_factory=list)   # (ruta, sitios donde se borró)
    repos_ocupados: list[str] = field(default_factory=list)
    repos_ignorados: list[str] = field(default_factory=list)
    no_disponibles: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    error: str | None = None
    pasos: list[dict] = field(default_factory=list)       # para «Deshacer»: lo enviado a la papelera
    segundos: float = 0.0

    @property
    def hubo_cambios(self) -> bool:
        return bool(self.copiados or self.movidos or self.a_papelera or self.conflictos)

    def resumen(self) -> str:
        partes = []
        for sitio in sorted(set(self.copiados) | set(self.movidos)):
            p = []
            if self.copiados[sitio]:
                p.append(f'{self.copiados[sitio]} copiado{"s" if self.copiados[sitio] != 1 else ""}')
            if self.movidos[sitio]:
                p.append(f'{self.movidos[sitio]} movido{"s" if self.movidos[sitio] != 1 else ""} o renombrado'
                         f'{"s" if self.movidos[sitio] != 1 else ""}')
            partes.append(f'{sitio} ' + ', '.join(p))
        if self.a_papelera:
            partes.append(f'{len(self.a_papelera)} a la papelera')
        if self.conflictos:
            partes.append(f'{len(self.conflictos)} conflicto{"s" if len(self.conflictos) != 1 else ""}')
        if self.sin_espacio:
            partes.append('sin espacio en ' + ', '.join(self.sin_espacio))
        if self.retenidos:
            partes.append(f'{len(self.retenidos)} borrados esperando tu confirmación')
        if self.errores:
            partes.append(f'{len(self.errores)} no se pudieron (se reintenta)')
        return '; '.join(partes) or 'todo igual'


def nombre_conflicto(ruta: str, ocupadas: set[str], hoy: str) -> str:
    base, ext = partir_ext(ruta)
    n = 1
    while True:
        cand = f'{base} (conflicto {hoy}{"" if n == 1 else f" {n}"}){ext}'
        if clave(cand) not in ocupadas:
            return cand
        n += 1


class Sincronizador:
    def __init__(self, cfg, historial=None, indice=None, ahora=time.time):
        self.cfg, self.historial, self.indice, self.ahora = cfg, historial, indice, ahora
        self.replicas = [Replica('OneDrive', cfg.onedrive, cfg.carpetas_indice)] + \
                        [Replica(c['nombre'], c['raiz'], c['carpetas']) for c in cfg.copias]
        self._lock = threading.Lock()
        self.db = sqlite3.connect(os.path.join(cfg.datos, 'sincro.sqlite'), check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS estado (replica TEXT, clave TEXT, ruta TEXT, tam INTEGER, mtime REAL,
                                               hash TEXT, dir INTEGER, PRIMARY KEY (replica, clave));
            CREATE TABLE IF NOT EXISTS base (clave TEXT PRIMARY KEY, ruta TEXT, hash TEXT);
            CREATE TABLE IF NOT EXISTS decisiones (clave TEXT PRIMARY KEY, accion TEXT);
            CREATE TABLE IF NOT EXISTS info (clave TEXT PRIMARY KEY, valor TEXT);
        ''')

    def excluir(self, por_copia: dict[str, set[str]]) -> None:
        """Archivos que no deben ir a cierta copia (los Word de los Docs de esa cuenta)."""
        for r in self.replicas:
            r.excluidas = set(por_copia.get(r.nombre, set()))

    # ── Lectura y escritura del estado ──────────────────────────────────────
    def inicializado(self) -> bool:
        return self.db.execute('SELECT 1 FROM base LIMIT 1').fetchone() is not None

    def _leer_estado(self) -> dict[str, dict[str, Entrada]]:
        res: dict[str, dict[str, Entrada]] = {}
        for rep, k, ruta, tam, mtime, h, d in self.db.execute('SELECT * FROM estado'):
            res.setdefault(rep, {})[k] = Entrada(ruta, tam, mtime, h, bool(d))
        return res

    def _leer_base(self) -> dict[str, Objetivo]:
        return {k: Objetivo(h, ruta) for k, ruta, h in self.db.execute('SELECT * FROM base')}

    def decisiones(self) -> dict[str, str]:
        return dict(self.db.execute('SELECT clave, accion FROM decisiones'))

    def decidir(self, claves: list[str], accion: str) -> None:
        """accion: 'borrar' (mandarlos a la papelera en todos los sitios) o 'recuperar'."""
        with self._lock, self.db:
            self.db.executemany('INSERT OR REPLACE INTO decisiones VALUES (?,?)', [(k, accion) for k in claves])

    def info(self, k: str, defecto: str = '') -> str:
        f = self.db.execute('SELECT valor FROM info WHERE clave=?', (k,)).fetchone()
        return f[0] if f else defecto

    def _poner_info(self, k: str, v: str) -> None:
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO info VALUES (?,?)', (k, v))

    def _guardar(self, estado: dict[str, dict[str, Entrada]], base: dict[str, Objetivo], hechas: set[str],
                 antes: dict[str, dict[str, Entrada]] | None = None, base_antes: dict[str, Objetivo] | None = None) -> None:
        """Guarda el estado. Con «antes», solo escribe lo que ha cambiado (casi nada en una pasada normal)."""
        fila = lambda o: (o.ruta, o.tam, o.mtime, o.hash, int(o.dir))
        with self.db:
            for rep, entradas in estado.items():
                viejo = (antes or {}).get(rep) if antes is not None else None
                if viejo is None:
                    self.db.execute('DELETE FROM estado WHERE replica=?', (rep,))
                    cambiadas, quitadas = entradas, []
                else:
                    cambiadas = {k: e for k, e in entradas.items() if k not in viejo or fila(viejo[k]) != fila(e)}
                    quitadas = [k for k in viejo if k not in entradas]
                self.db.executemany('DELETE FROM estado WHERE replica=? AND clave=?', [(rep, k) for k in quitadas])
                self.db.executemany('INSERT OR REPLACE INTO estado VALUES (?,?,?,?,?,?,?)',
                                    [(rep, k, *fila(e)) for k, e in cambiadas.items()])
            if base_antes is None:
                self.db.execute('DELETE FROM base')
                cambiadas_b, quitadas_b = base, []
            else:
                cambiadas_b = {k: o for k, o in base.items()
                               if k not in base_antes or (base_antes[k].ruta, base_antes[k].hash) != (o.ruta, o.hash)}
                quitadas_b = [k for k in base_antes if k not in base]
            self.db.executemany('DELETE FROM base WHERE clave=?', [(k,) for k in quitadas_b])
            self.db.executemany('INSERT OR REPLACE INTO base VALUES (?,?,?)',
                                [(k, o.ruta, o.hash) for k, o in cambiadas_b.items()])
            if hechas:
                self.db.executemany('DELETE FROM decisiones WHERE clave=?', [(k,) for k in hechas])

    # ── Escaneo ─────────────────────────────────────────────────────────────
    def escanear(self, rep: Replica) -> dict[str, Entrada] | None:
        """Tamaño y fecha de todo lo que cubre ese sitio. None si algo no se puede leer (el sitio se salta)."""
        res: dict[str, Entrada] = {}
        for top in rep.carpetas:
            raiz = rep.ruta(top)
            if not os.path.isdir(raiz):
                continue
            res[clave(top)] = Entrada(top, dir=True, hash=DIR)
            pila = [raiz]
            while pila:
                d = pila.pop()
                try:
                    with os.scandir(ruta_larga(d)) as it:
                        entradas = list(it)
                except OSError as e:
                    log.warning('No puedo leer %s: %s', d, e)
                    return None
                for e in entradas:
                    p = os.path.join(d, e.name)
                    rel = os.path.relpath(p, rep.raiz)
                    try:
                        if e.is_dir(follow_symlinks=False):
                            if e.name.lower() not in EXCLUIR_DIRS:
                                res[clave(rel)] = Entrada(rel, dir=True, hash=DIR)
                                pila.append(p)
                        elif not excluido(e.name) and clave(rel) not in rep.excluidas:
                            st = e.stat(follow_symlinks=False)
                            res[clave(rel)] = Entrada(rel, st.st_size, st.st_mtime)
                    except OSError:
                        return None
        return res

    def _huella(self, rep: Replica, e: Entrada) -> str | None:
        if rep.nombre == 'OneDrive' and self.indice is not None:
            if h := self.indice.huella_de(e.ruta, e.tam, e.mtime):
                return h
        try:
            return huella(rep.ruta(e.ruta))
        except OSError:
            return None

    # ── Estado inicial ──────────────────────────────────────────────────────
    def crear_estado_inicial(self, muestra: int = 300) -> tuple[bool, str]:
        """Si los tres sitios son iguales (nombres, tamaños y fechas), guarda el estado sin copiar nada.

        Verifica por huella una muestra de archivos de las copias."""
        scans = {}
        for r in self.replicas:
            s = self.escanear(r) if os.path.isdir(r.raiz) else None
            if s is None:
                return False, f'{r.nombre} no está disponible'
            scans[r.nombre] = s
        so = scans['OneDrive']
        repos = [k[:-len(SEP + '.git')] for k, e in so.items() if e.dir and k.endswith(SEP + '.git')]

        def tolerable(k, a, b):
            """Dentro de un repo (van de OneDrive a las copias) o una carpeta vacía que falta: lo arregla la 1.ª pasada."""
            return any(k.startswith(rk + SEP) for rk in repos) or (a is not None and a.dir and b is None)
        diferencias, a_arreglar = [], 0
        for r in self.replicas[1:]:
            s = scans[r.nombre]
            esperado = {k for k in so if r.cubre(k)}
            for k in sorted(esperado ^ set(s)):
                if tolerable(k, so.get(k), s.get(k)):
                    a_arreglar += 1
                    continue
                diferencias.append(f'{r.nombre}: «{(so.get(k) or s.get(k)).ruta}» solo está en '
                                   f'{"OneDrive" if k in so else r.nombre}')
            for k in esperado & set(s):
                a, b = so[k], s[k]
                if a.dir != b.dir or (not a.dir and (a.tam != b.tam or abs(a.mtime - b.mtime) > 2)):
                    if tolerable(k, a, b):
                        a_arreglar += 1
                        b.hash = None                    # se calculará la suya
                        continue
                    diferencias.append(f'{r.nombre}: «{a.ruta}» distinto (tamaño o fecha)')
        if diferencias:
            return False, 'No son iguales:\n' + '\n'.join(diferencias[:30])
        for e in so.values():
            if not e.dir:
                e.hash = self._huella(self.replicas[0], e)
                if e.hash is None:
                    return False, f'No puedo leer «{e.ruta}» en OneDrive'
        comprobados = 0
        for r in self.replicas[1:]:
            s = scans[r.nombre]
            archivos = [k for k, e in s.items() if not e.dir]
            iguales = [k for k in archivos if k in so and s[k].tam == so[k].tam]
            for k in random.sample(iguales, min(muestra // max(1, len(self.replicas) - 1), len(iguales))):
                h = self._huella(r, s[k])
                if h != so[k].hash:
                    return False, f'{r.nombre}: «{s[k].ruta}» tiene el mismo tamaño y fecha pero distinto contenido'
                comprobados += 1
            for k, e in s.items():
                if e.dir:
                    continue
                if k in so and not so[k].dir and e.tam == so[k].tam and abs(e.mtime - so[k].mtime) <= 2:
                    e.hash = so[k].hash
                else:
                    e.hash = self._huella(r, e)
        base = {k: Objetivo(e.hash, e.ruta) for k, e in so.items()}
        self._guardar(scans, base, set())
        self._poner_info('ultima', str(self.ahora()))
        n = sum(1 for e in so.values() if not e.dir)
        return True, (f'Estado inicial guardado: {n} archivos; {comprobados} comprobados por huella en las copias'
                      + (f'; {a_arreglar} diferencias dentro de repos o carpetas vacías, que arreglará la primera pasada'
                         if a_arreglar else ''))

    # ── Pasada ──────────────────────────────────────────────────────────────
    def pasada(self, simulacion: bool | None = None) -> Informe:
        with self._lock:
            t0 = time.time()
            inf = self._pasada(self.cfg.sincro_simulacion if simulacion is None else simulacion)
            inf.segundos = time.time() - t0
            return inf

    def _pasada(self, simulacion: bool) -> Informe:
        inf = Informe(simulacion=simulacion)
        O = self.replicas[0]
        estado, base, decis = self._leer_estado(), self._leer_base(), self.decisiones()
        ahora = self.ahora()
        hoy = datetime.date.fromtimestamp(ahora).isoformat()

        # 1. Escaneo
        scans: dict[str, dict[str, Entrada]] = {}
        for r in self.replicas:
            s = self.escanear(r) if os.path.isdir(r.raiz) else None
            if s is None:
                inf.no_disponibles.append(r.nombre)
                continue
            antes = estado.get(r.nombre, {})
            faltan = [c for c in r.carpetas if clave(c) not in s and clave(c) in antes]
            if faltan:     # una carpeta principal entera desaparecida: algo raro, mejor no tocar ese sitio
                inf.avisos.append(f'En {r.nombre} falta la carpeta «{faltan[0]}»: esta vez no toco {r.nombre}')
                inf.no_disponibles.append(r.nombre)
                continue
            for k, e in s.items():                  # huellas que ya se conocen (no ha cambiado)
                p = antes.get(k)
                if not e.dir and p and not p.dir and p.tam == e.tam and abs(p.mtime - e.mtime) < 0.001:
                    e.hash = p.hash
            scans[r.nombre] = s
        if O.nombre not in scans:
            inf.error = 'OneDrive no está disponible'
            return inf
        disp = [r for r in self.replicas if r.nombre in scans]
        so = scans[O.nombre]

        # 2. Repos git: solo de OneDrive a las copias, y solo si están quietos
        repos = sorted(k[:-len(SEP + '.git')] for k, e in so.items() if e.dir and k.endswith(SEP + '.git'))
        ocupados = set()
        for rk in repos:
            dentro = [e for k, e in so.items() if k.startswith(rk + SEP) and not e.dir]
            lock = (rk + SEP + '.git' + SEP + 'index.lock') in so
            if lock or any(ahora - e.mtime < self.cfg.minutos_repo * 60 for e in dentro):
                ocupados.add(rk)
                inf.repos_ocupados.append(so[rk].ruta)

        def repo_de(k):
            return next((rk for rk in repos if k.startswith(rk + SEP)), None)

        omitir: set[str] = set()

        def cambio(r: Replica, k: str):
            if not r.cubre(k):
                return None
            e, p = scans[r.nombre].get(k), estado.get(r.nombre, {}).get(k)
            if e and not e.dir and e.hash is None:
                e.hash = self._huella(r, e)
                if e.hash is None:                  # abierto o ilegible: se reintenta
                    inf.errores.append(f'{r.nombre}: no puedo leer «{e.ruta}»')
                    omitir.add(k)
                    return None
            if e and p and not e.dir and not p.dir and e.tam == 0 and p.tam > 0:
                # Un archivo que de repente se queda vacío suele ser un fallo (de Drive, de un programa…):
                # no se propaga ni pisa las versiones buenas de los otros sitios.
                inf.avisos.append(f'«{e.ruta}» se ha quedado vacío en {r.nombre}: no lo copio a los demás sitios')
                omitir.add(k)
                return None
            if e and not p:
                return 'nuevo'
            if p and not e:
                return 'borrado'
            if e and p and (e.dir != p.dir or e.hash != p.hash):
                return 'mod'
            return None

        # 3. Objetivo de cada archivo
        claves = set(base)
        for r in disp:
            claves |= {k for k in scans[r.nombre] if r.cubre(k)}
            claves |= {k for k in estado.get(r.nombre, {}) if r.cubre(k)}
        T: dict[str, Objetivo] = {}
        ocupadas = set(claves)
        for k in sorted(claves):
            rk = repo_de(k)
            if rk and rk in ocupados:
                omitir.add(k)
                continue
            cs = {r.nombre: c for r in disp if (c := cambio(r, k))}
            if k in omitir:
                continue
            if rk:                                       # repo quieto: manda OneDrive
                e = so.get(k)
                T[k] = Objetivo(e.hash, e.ruta, O.nombre) if e else Objetivo(None, base[k].ruta if k in base else k)
                for sitio in cs:
                    if sitio != O.nombre:
                        inf.repos_ignorados.append(f'{sitio}: «{scans[sitio][k].ruta if k in scans[sitio] else k}»')
                continue
            if not cs:
                if k in base:
                    T[k] = base[k]
                else:      # no ha cambiado en ningún sitio pero ya se acordó borrarlo (p. ej. H: estaba desconectada)
                    ruta = next(scans[r.nombre][k].ruta for r in disp if k in scans[r.nombre])
                    T[k] = Objetivo(None, ruta)
                continue
            presentes = {sitio: scans[sitio][k] for sitio, c in cs.items() if c != 'borrado'}
            if not presentes:                            # solo borrados
                if decis.get(k) == 'recuperar' and k in base:
                    T[k] = base[k]
                else:
                    T[k] = Objetivo(None, base[k].ruta if k in base else next(
                        estado[s][k].ruta for s in cs))
                continue
            if len({e.dir for e in presentes.values()}) > 1:
                inf.avisos.append(f'«{k}» es carpeta en un sitio y archivo en otro: no lo toco')
                omitir.add(k)
                continue
            hashes = {e.hash for e in presentes.values()}
            if len(hashes) == 1:
                sitio = O.nombre if O.nombre in presentes else next(iter(presentes))
                e = presentes[sitio]
                T[k] = Objetivo(e.hash, e.ruta, sitio)
                continue
            # Conflicto: el más reciente se queda el nombre; los demás, con «(conflicto AAAA-MM-DD)».
            orden = sorted(presentes.items(), key=lambda x: -x[1].mtime)
            sitio, e = orden[0]
            T[k] = Objetivo(e.hash, e.ruta, sitio)
            vistos = {e.hash}
            for sitio, e in orden[1:]:
                if e.hash in vistos:
                    continue
                vistos.add(e.hash)
                ruta_c = nombre_conflicto(e.ruta, ocupadas, hoy)
                ocupadas.add(clave(ruta_c))
                T[clave(ruta_c)] = Objetivo(e.hash, ruta_c, sitio, e.ruta)
                inf.conflictos.append(ruta_c)
        # Una carpeta borrada en un sitio sigue existiendo si dentro queda algo que debe existir.
        vivas = set()
        for k, t in T.items():
            if t.hash:
                partes = k.split(SEP)
                vivas |= {SEP.join(partes[:i]) for i in range(1, len(partes))}
        for k, t in T.items():
            if t.hash is None and k in vivas:
                T[k] = Objetivo(DIR, t.ruta)

        # 4. Plan para cada sitio
        planes = {}
        borrados_por_clave: dict[str, list[str]] = {}
        for r in disp:
            planes[r.nombre] = self._planear(r, scans[r.nombre], estado.get(r.nombre, {}), T, omitir, repo_de, inf)
            for k in planes[r.nombre]['papelera']:
                borrados_por_clave.setdefault(k, []).append(r.nombre)

        # 5. Freno de borrados masivos
        sin_permiso = [k for k in borrados_por_clave if decis.get(k) != 'borrar']
        retenidos: set[str] = set()
        if len(sin_permiso) > self.cfg.max_borrados:
            retenidos = set(sin_permiso)
            for k in sorted(retenidos):
                donde = [r.nombre for r in disp if r.cubre(k) and cambio(r, k) == 'borrado']
                inf.retenidos.append((T[k].ruta if k in T else k, donde))
            for p in planes.values():
                p['papelera'] = [k for k in p['papelera'] if k not in retenidos]

        # 6. Ejecución (OneDrive primero: recoger; luego las copias: repartir)
        nuevo_estado = {r.nombre: dict(estado.get(r.nombre, {})) for r in disp}
        congelar = omitir | retenidos
        for r in disp:
            ne, s = nuevo_estado[r.nombre], scans[r.nombre]
            for k in set(ne) | set(s):
                if k in congelar or not r.cubre(k):
                    continue
                if k in s and (s[k].dir or s[k].hash):
                    ne[k] = s[k]
                elif k in s:                              # sin huella todavía (no hizo falta): calcularla
                    s[k].hash = self._huella(r, s[k])
                    if s[k].hash:
                        ne[k] = s[k]
                else:
                    ne.pop(k, None)
        for r in disp:
            self._ejecutar(r, planes[r.nombre], T, scans, nuevo_estado, simulacion, inf)

        # 7. Nuevo estado y base
        if simulacion:
            return inf
        nueva_base = dict(base)
        for k, t in T.items():
            if k in congelar:
                continue
            if t.hash is None:
                nueva_base.pop(k, None)
            else:
                nueva_base[k] = Objetivo(t.hash, t.ruta)
        hechas = {k for k in decis if k not in retenidos}
        self._guardar(nuevo_estado, nueva_base, hechas, estado, base)
        self._poner_info('ultima', str(ahora))
        return inf

    def _planear(self, r: Replica, s, est, T, omitir, repo_de, inf) -> dict:
        crear_dirs, quitar_dirs, copiar, papelera_, mover = [], [], [], [], []
        necesita: dict[str, list[str]] = {}
        sobra: dict[str, list[str]] = {}
        reemplazables: dict[str, list[str]] = {}      # su contenido se va a sustituir: se puede apartar moviéndolo
        for k, t in T.items():
            if k in omitir or not r.cubre(k):
                continue
            e = s.get(k)
            if t.hash == DIR:
                if not e:
                    crear_dirs.append(k)
                continue
            if t.hash is None:
                if e and e.dir:
                    quitar_dirs.append(k)
                elif e:
                    if e.hash is None:
                        e.hash = self._huella(r, e)
                    sobra.setdefault(e.hash or '?', []).append(k)
                continue
            if e and e.dir:
                inf.avisos.append(f'{r.nombre}: «{e.ruta}» es una carpeta y debería ser un archivo')
                continue
            if e and e.hash is None:
                e.hash = self._huella(r, e)
            if not e or e.hash != t.hash:
                if e and repo_de(k) and r.nombre != 'OneDrive' and (k not in est or est[k].hash != e.hash):
                    papelera_.append(k)                  # cambiado a mano en la copia de un repo: a la papelera
                elif e:
                    reemplazables.setdefault(e.hash, []).append(k)
                necesita.setdefault(t.hash, []).append(k)
        # Movimientos: lo que sobra (o se va a sustituir) con la misma huella que lo que falta.
        # Así un renombrado se mueve en vez de copiarse, y en un conflicto la versión que pierde se
        # aparta con su nombre «(conflicto …)» antes de copiar encima la que gana.
        movidos_de = set()
        for h, ks in necesita.items():
            for k in list(ks):
                if k in s and k not in movidos_de:
                    continue                             # el destino está ocupado (se sustituye)
                libres = [x for x in sobra.get(h, []) + reemplazables.get(h, []) if x not in movidos_de]
                if not libres:
                    continue
                nombre = k.rsplit(SEP, 1)[-1]
                viejo = next((x for x in libres if x.rsplit(SEP, 1)[-1] == nombre), libres[0])
                movidos_de.add(viejo)
                if viejo in sobra.get(h, []):
                    sobra[h].remove(viejo)
                ks.remove(k)
                mover.append((viejo, k))
        renombrar_dirs, mover = self._agrupar_carpetas(mover, s, T)
        # Las carpetas que se renombran enteras no hay que crearlas ni quitarlas aparte.
        crear_dirs = [k for k in crear_dirs if not any(k == b or k.startswith(b + SEP) for _, b in renombrar_dirs)]
        quitar_dirs = [k for k in quitar_dirs if not any(k == a or k.startswith(a + SEP) for a, _ in renombrar_dirs)]
        for h, ks in necesita.items():
            copiar += ks
        for ks in sobra.values():
            papelera_ += ks
        return {'crear_dirs': sorted(crear_dirs, key=len), 'renombrar_dirs': renombrar_dirs, 'mover': mover,
                'copiar': copiar, 'papelera': papelera_, 'quitar_dirs': sorted(quitar_dirs, key=len, reverse=True)}

    @staticmethod
    def _agrupar_carpetas(movs, s, T):
        """Si se ha renombrado o movido una carpeta entera, se renombra la carpeta (una sola operación)."""
        grupos: dict[tuple[str, str], list] = {}
        for viejo, nuevo in movs:
            a, b = s[viejo].ruta.split(SEP), T[nuevo].ruta.split(SEP)
            while len(a) > 1 and len(b) > 1 and clave(a[-1]) == clave(b[-1]):
                a, b = a[:-1], b[:-1]
            if len(a) < len(s[viejo].ruta.split(SEP)):          # comparten al menos el nombre del archivo
                grupos.setdefault((SEP.join(a), SEP.join(b)), []).append((viejo, nuevo))
        renombres, hechos = [], set()
        for (da, db), lista in sorted(grupos.items(), key=lambda x: x[0][0].count(SEP)):
            ka, kb = clave(da), clave(db)
            if any(ka == h or ka.startswith(h + SEP) for h, _ in renombres):
                continue
            archivos = {k for k, e in s.items() if k.startswith(ka + SEP) and not e.dir}
            if ka in s and kb not in s and not any(k.startswith(kb + SEP) for k in s) \
                    and archivos == {v for v, _ in lista}:
                renombres.append((ka, kb))
                hechos |= {v for v, _ in lista}
        return [(ka, kb) for ka, kb in renombres], [m for m in movs if m[0] not in hechos]

    def _ejecutar(self, r: Replica, plan, T, scans, nuevo_estado, simulacion, inf):
        O = self.replicas[0]
        ne, s = nuevo_estado[r.nombre], scans[r.nombre]

        def anotar(texto):
            inf.plan.append(f'[{r.nombre}] {texto}')

        def poner(k, ruta, h, es_dir=False):
            if es_dir:
                ne[k] = Entrada(ruta, dir=True, hash=DIR)
                return
            st = os.stat(ruta_larga(r.ruta(ruta)))
            ne[k] = Entrada(ruta, st.st_size, st.st_mtime, h)

        for k in plan['crear_dirs']:
            anotar(f'crear carpeta «{T[k].ruta}»')
            if not simulacion:
                try:
                    os.makedirs(ruta_larga(r.ruta(T[k].ruta)), exist_ok=True)
                    poner(k, T[k].ruta, DIR, True)
                except OSError as e:
                    inf.errores.append(f'{r.nombre}: crear «{T[k].ruta}»: {e}')
        for ka, kb in plan['renombrar_dirs']:
            viejo, nuevo = s[ka].ruta, T[kb].ruta if kb in T else self._ruta_dir(kb, T)
            anotar(f'renombrar carpeta «{viejo}» → «{nuevo}»')
            if simulacion:
                inf.movidos[r.nombre] += 1
                continue
            try:
                os.makedirs(ruta_larga(os.path.dirname(r.ruta(nuevo))), exist_ok=True)
                os.rename(ruta_larga(r.ruta(viejo)), ruta_larga(r.ruta(nuevo)))
                for k in [x for x in ne if x == ka or x.startswith(ka + SEP)]:
                    e = ne.pop(k)
                    k2 = kb + k[len(ka):]
                    e.ruta = nuevo + e.ruta[len(viejo):]
                    ne[k2] = e
                inf.movidos[r.nombre] += 1
            except OSError as e:
                inf.errores.append(f'{r.nombre}: renombrar «{viejo}»: {e}')
        # Contenidos que este sitio aún necesita: nunca se sobrescribe un archivo que tenga uno de ellos.
        faltan = Counter(T[k].hash for k in plan['copiar'])
        for viejo, nuevo in plan['mover']:
            de, a = s[viejo].ruta, T[nuevo].ruta
            anotar(f'mover «{de}» → «{a}»')
            if simulacion:
                inf.movidos[r.nombre] += 1
                continue
            try:
                os.makedirs(ruta_larga(os.path.dirname(r.ruta(a))), exist_ok=True)
                os.rename(ruta_larga(r.ruta(de)), ruta_larga(r.ruta(a)))
                if ne.get(viejo) and ne[viejo].ruta == de:
                    ne.pop(viejo)
                poner(nuevo, a, T[nuevo].hash)
                inf.movidos[r.nombre] += 1
            except OSError as e:
                faltan[T[nuevo].hash] += 1
                inf.errores.append(f'{r.nombre}: mover «{de}»: {e}')
        papelera_primero = [k for k in plan['papelera'] if k in plan['copiar']]   # repos tocados en la copia
        self._papelera(r, papelera_primero, s, ne, simulacion, inf, anotar)
        espacio = None
        for k in plan['copiar']:
            t = T[k]
            fuente = self._fuente(k, t, r, scans, nuevo_estado)
            if fuente is None:
                inf.errores.append(f'{r.nombre}: no encuentro de dónde copiar «{t.ruta}»')
                continue
            sitio, ruta_fuente = fuente
            tam = os.path.getsize(ruta_larga(ruta_fuente)) if os.path.exists(ruta_larga(ruta_fuente)) else 0
            if r.nombre != O.nombre:
                if espacio is None:
                    try:
                        espacio = shutil.disk_usage(r.raiz).free
                    except OSError:
                        espacio = 0
                if tam > espacio - MARGEN_ESPACIO:
                    inf.sin_espacio[r.nombre] += 1
                    continue
                espacio -= tam
            destino = t.ruta if k not in s else s[k].ruta
            anotar(f'copiar «{t.ruta}» desde {sitio}')
            if simulacion:
                inf.copiados[r.nombre] += 1
                continue
            actual = ne.get(k)
            if actual and not actual.dir and actual.hash != t.hash and faltan[actual.hash] > 0:
                inf.errores.append(f'{r.nombre}: conservo «{actual.ruta}» hasta poder guardar su otra versión')
                continue
            if r.nombre == O.nombre and actual and not actual.dir and sitio != O.nombre:
                # La versión de OneDrive que se sustituye por otra que llega de G: o H: va antes a la Papelera:
                # si el cambio venía de un error, la buena se recupera.
                try:
                    fecha = papelera.enviar(r.ruta(destino))
                    inf.pasos.append({'op': 'papelera', 'ruta': r.ruta(destino), 'fecha': fecha})
                except OSError as e:
                    inf.errores.append(f'{r.nombre}: no puedo apartar «{destino}» antes de sustituirlo: {e}')
                    continue
            try:
                self._copiar(ruta_fuente, r.ruta(destino))
                poner(k, destino, t.hash)
                faltan[t.hash] -= 1
                inf.copiados[r.nombre] += 1
                if r.nombre == O.nombre and self.indice is not None:
                    self.indice.anadir(r.ruta(destino), t.hash)
            except OSError as e:
                inf.errores.append(f'{r.nombre}: copiar «{t.ruta}»: {e}')
        self._papelera(r, [k for k in plan['papelera'] if k not in papelera_primero], s, ne, simulacion, inf, anotar)
        for k in plan['quitar_dirs']:
            ruta = s[k].ruta
            try:
                vacia = not os.listdir(ruta_larga(r.ruta(ruta)))
            except OSError:
                continue
            if not vacia:
                continue
            anotar(f'quitar carpeta vacía «{ruta}»')
            if not simulacion:
                try:
                    os.rmdir(ruta_larga(r.ruta(ruta)))
                    ne.pop(k, None)
                except OSError as e:
                    inf.errores.append(f'{r.nombre}: quitar carpeta «{ruta}»: {e}')

    def _papelera(self, r, claves, s, ne, simulacion, inf, anotar):
        for k in claves:
            if k not in s:
                continue
            ruta = s[k].ruta
            anotar(f'a la papelera «{ruta}»')
            inf.a_papelera.append(f'{r.nombre}: {ruta}')
            if simulacion:
                continue
            try:
                fecha = papelera.enviar(r.ruta(ruta))
                inf.pasos.append({'op': 'papelera', 'ruta': r.ruta(ruta), 'fecha': fecha})
                ne.pop(k, None)
                if r.nombre == 'OneDrive' and self.indice is not None:
                    self.indice.quitar(r.ruta(ruta))
            except OSError as e:
                inf.a_papelera.pop()
                inf.errores.append(f'{r.nombre}: a la papelera «{ruta}»: {e}')

    def _fuente(self, k, t, r, scans, nuevo_estado):
        """De dónde copiar: de OneDrive si ya lo tiene (estrella); si no, del sitio donde cambió."""
        candidatos = ['OneDrive'] + [x for x in (t.fuente,) if x and x != 'OneDrive']
        for sitio in candidatos:
            if sitio == r.nombre:
                continue
            for kk in [k] + ([clave(t.origen)] if t.origen else []):
                e = nuevo_estado.get(sitio, {}).get(kk)
                if e and not e.dir and e.hash == t.hash:
                    rep = next(x for x in self.replicas if x.nombre == sitio)
                    return sitio, rep.ruta(e.ruta)
        return None

    @staticmethod
    def _ruta_dir(k, T):
        hijo = next((t.ruta for kk, t in T.items() if kk.startswith(k + SEP)), None)
        return SEP.join(hijo.split(SEP)[:k.count(SEP) + 1]) if hijo else k

    @staticmethod
    def _copiar(origen: str, destino: str) -> None:
        """Copia segura: a un nombre temporal y, al acabar, se renombra (nunca queda un archivo a medias)."""
        os.makedirs(ruta_larga(os.path.dirname(destino)), exist_ok=True)
        tmp = destino + TMP
        shutil.copyfile(ruta_larga(origen), ruta_larga(tmp))
        try:
            shutil.copystat(ruta_larga(origen), ruta_larga(tmp))     # fecha y «solo lectura»
        except OSError:
            st = os.stat(ruta_larga(origen))
            os.utime(ruta_larga(tmp), (st.st_atime, st.st_mtime))
        if os.path.exists(ruta_larga(destino)) and not os.access(ruta_larga(destino), os.W_OK):
            os.chmod(ruta_larga(destino), stat.S_IWRITE | stat.S_IREAD)   # un Word de solo lectura que se actualiza
        try:
            os.replace(ruta_larga(tmp), ruta_larga(destino))
        except OSError:
            try:
                os.remove(ruta_larga(tmp))
            except OSError:
                pass
            raise

    def ultima(self) -> float:
        return float(self.info('ultima', '0') or 0)
