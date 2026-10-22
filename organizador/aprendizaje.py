"""aprendido.txt: lo que el programa sabe de dónde va cada cosa. El usuario puede editarlo."""
import logging
import os
import re
import threading
from collections import Counter, defaultdict

from . import origen
from .nombres import nfc

log = logging.getLogger(__name__)

CABECERA = """\
# Lo que el Organizador ha aprendido. Puedes editarlo con el Bloc de notas;
# los cambios se notan en la siguiente descarga, sin reiniciar nada.
#
# Cada línea es:  <tipo> <clave> = <carpeta dentro de OneDrive>
#   curso N       id de un curso de Aula Global → su asignatura
#   contexto N    un recurso o sección concreta de Aula Global
#   actividad N   una actividad de Aula Global (carpeta, tarea…)
#   web dominio   descargas de esa web
#
# Para que olvide algo, borra la línea. Las líneas con # delante no cuentan.
"""

_LINEA = re.compile(r'^\s*(curso|contexto|actividad|web)\s+(\S+)\s*=\s*(.+?)\s*$', re.I)


class Aprendido:
    def __init__(self, archivo: str, onedrive: str, simulacion: bool = False):
        self.archivo, self.onedrive, self.simulacion = archivo, onedrive, simulacion
        self.reglas: dict[tuple[str, str], str] = {}
        self._mtime = None
        self._lock = threading.Lock()

    def _recargar(self) -> None:
        try:
            mtime = os.path.getmtime(self.archivo)
        except OSError:
            self.reglas, self._mtime = {}, None
            return
        if mtime == self._mtime:
            return
        reglas = {}
        with open(self.archivo, encoding='utf-8-sig', errors='replace') as f:
            for linea in f:
                if m := _LINEA.match(linea):
                    reglas[(m.group(1).lower(), m.group(2).lower())] = nfc(m.group(3)).strip('\\ ')
        self.reglas, self._mtime = reglas, mtime

    def buscar(self, claves: list[tuple[str, str]]) -> list[tuple[tuple[str, str], str]]:
        """Reglas que encajan, en el orden de las claves (de más concreta a menos)."""
        with self._lock:
            self._recargar()
            return [(k, self.reglas[(k[0], k[1].lower())]) for k in claves if (k[0], k[1].lower()) in self.reglas]

    def aprender(self, reglas: dict[tuple[str, str], str]) -> None:
        """Añade o cambia reglas, conservando el resto del archivo tal cual."""
        if not reglas:
            return
        if self.simulacion:
            log.info('[simulación] aprendería: %s', reglas)
            return
        with self._lock:
            self._recargar()
            pendientes = {(t, c.lower()): d for (t, c), d in reglas.items()
                          if self.reglas.get((t, c.lower())) != d}
            if not pendientes:
                return
            lineas = []
            if os.path.exists(self.archivo):
                with open(self.archivo, encoding='utf-8-sig', errors='replace') as f:
                    lineas = f.read().splitlines()
            else:
                lineas = CABECERA.splitlines()
            for i, linea in enumerate(lineas):
                if (m := _LINEA.match(linea)) and (k := (m.group(1).lower(), m.group(2).lower())) in pendientes:
                    lineas[i] = f'{k[0]} {k[1]} = {pendientes.pop(k)}'
            if pendientes:
                lineas.append('')
                lineas += [f'{t} {c} = {d}' for (t, c), d in pendientes.items()]
            self._escribir(lineas)
            self._mtime = None

    def _escribir(self, lineas: list[str]) -> None:
        tmp = self.archivo + '.tmp'
        with open(tmp, 'w', encoding='utf-8', newline='\r\n') as f:
            f.write('\n'.join(lineas).rstrip() + '\n')
        os.replace(tmp, self.archivo)


def crear_inicial(archivo: str, onedrive: str, carpetas: list[str], ruta_uni: str,
                  webs_genericas: set[str], saltar: list[str]) -> int:
    """Primer aprendido.txt a partir del origen de las descargas que ya están ordenadas."""
    from .carpetas import asignatura_de
    saltar = {os.path.normcase(os.path.join(onedrive, s)) for s in saltar}
    votos: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for carpeta in carpetas:
        for raiz, dirs, archivos in os.walk(os.path.join(onedrive, carpeta)):
            dirs[:] = [d for d in dirs if d != '.git'
                       and os.path.normcase(os.path.join(raiz, d)) not in saltar]
            for a in archivos:
                ruta = os.path.join(raiz, a)
                o = origen.leer(ruta)
                if not o.web and not o.host_url:
                    continue
                destino = os.path.relpath(raiz, onedrive)
                asig = asignatura_de(ruta, ruta_uni)
                asig_rel = os.path.relpath(asig.ruta, onedrive) if asig else None
                for tipo, valor in o.claves():
                    if tipo == 'web' and (o.web in webs_genericas or not o.web):
                        continue
                    if tipo == 'curso' or (tipo == 'contexto' and o.componente == 'course'):
                        if asig_rel:
                            votos[(tipo, valor)][asig_rel] += 1
                    else:
                        votos[(tipo, valor)][destino] += 1
    reglas = {}
    for k, cont in votos.items():
        destino, n = cont.most_common(1)[0]
        if k[0] == 'web' and (n < 2 or n < sum(cont.values()) * 0.8):
            continue                     # una web con destinos variados no enseña nada
        if k[0] != 'web' and len(cont) > 1:
            destino = os.path.commonpath(list(cont))   # el recurso aparece en varias categorías
        reglas[k] = nfc(destino)
    orden = {'curso': 0, 'contexto': 1, 'actividad': 2, 'web': 3}
    lineas = CABECERA.splitlines() + ['', '# Creado a partir de las descargas que ya estaban ordenadas.']
    lineas += [f'{t} {c} = {d}' for (t, c), d in sorted(reglas.items(), key=lambda x: (orden[x[0][0]], x[1], x[0][1]))]
    tmp = archivo + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\r\n') as f:
        f.write('\n'.join(lineas) + '\n')
    os.replace(tmp, archivo)
    return len(reglas)
