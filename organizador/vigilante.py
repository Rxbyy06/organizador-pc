"""Vigila Descargas con eventos del sistema y avisa cuando una descarga ha terminado."""
import logging
import os
import threading
import time

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .huellas import ignorado
from .nombres import ruta_larga

log = logging.getLogger(__name__)
TEMPORALES = ('.crdownload', '.tmp', '.part', '.partial', '.download', '.opdownload')


class Vigilante(FileSystemEventHandler):
    """Llama a «nueva(ruta)» cuando un archivo de Descargas lleva quieto unos segundos."""

    def __init__(self, cfg, nueva, salida):
        self.cfg, self.nueva, self.salida = cfg, nueva, salida
        self.carpeta = os.path.normpath(cfg.descargas)
        self._candidatos: dict[str, tuple[int, float, float]] = {}   # ruta → (tamaño, mtime, quieto desde)
        self._lock = threading.Lock()
        self._obs = Observer()
        self._parar = threading.Event()
        self._hilo: threading.Thread | None = None

    def interesa(self, ruta: str) -> bool:
        nombre = os.path.basename(ruta)
        if os.path.normpath(os.path.dirname(ruta)) != self.carpeta:
            return False                       # solo lo que está directamente en Descargas
        if nombre in self.cfg.ignorar or ignorado(nombre) or nombre.lower().endswith(TEMPORALES):
            return False
        return not nombre.startswith('.')

    def arrancar(self) -> None:
        self._obs.schedule(self, self.carpeta, recursive=False)
        self._obs.start()
        self._hilo = threading.Thread(target=self._comprobar, name='descargas-estables', daemon=True)
        self._hilo.start()

    def parar(self) -> None:
        self._parar.set()
        self._obs.stop()

    def vivo(self) -> bool:
        """¿Siguen en marcha los avisos de Windows y el hilo que espera a que acabe cada descarga?"""
        return (self._hilo is not None and self._hilo.is_alive() and self._obs.is_alive()
                and all(e.is_alive() for e in self._obs.emitters))

    def vigilar(self, ruta: str) -> None:
        if self.interesa(ruta):
            with self._lock:
                self._candidatos.setdefault(ruta, (-1, 0, 0))

    # Eventos de watchdog
    def on_created(self, e):
        if not e.is_directory:
            self.vigilar(e.src_path)

    def on_modified(self, e):
        if not e.is_directory:
            self.vigilar(e.src_path)

    def on_moved(self, e):
        if not e.is_directory:
            self._fuera(e.src_path)
            self.vigilar(e.dest_path)

    def on_deleted(self, e):
        self._fuera(e.src_path)

    def _fuera(self, ruta: str) -> None:
        with self._lock:
            self._candidatos.pop(ruta, None)
        if os.path.normpath(os.path.dirname(ruta)) == self.carpeta:
            self.salida(ruta)

    def _comprobar(self) -> None:
        while not self._parar.wait(1):
            try:
                self._repasar()
            except Exception:
                log.exception('Error vigilando Descargas')

    def _repasar(self) -> None:
        ahora = time.time()
        with self._lock:
            candidatos = dict(self._candidatos)
        for ruta, (tam, mtime, desde) in candidatos.items():
            try:
                st = os.stat(ruta_larga(ruta))
            except OSError:
                with self._lock:
                    self._candidatos.pop(ruta, None)
                continue
            if (st.st_size, st.st_mtime) != (tam, mtime):
                with self._lock:
                    self._candidatos[ruta] = (st.st_size, st.st_mtime, ahora)
                continue
            # Firefox crea el archivo vacío y descarga en «.part»: esperar a que este desaparezca.
            if os.path.exists(ruta + '.part') or (st.st_size == 0 and ahora - desde < 30):
                continue
            if ahora - desde < self.cfg.segundos_estable or not _se_puede_abrir(ruta):
                continue
            with self._lock:
                self._candidatos.pop(ruta, None)
            try:
                self.nueva(ruta)
            except Exception:
                log.exception('Error con la descarga %s', ruta)


def _se_puede_abrir(ruta: str) -> bool:
    try:
        with open(ruta_larga(ruta), 'rb'):
            return True
    except OSError:
        return False
