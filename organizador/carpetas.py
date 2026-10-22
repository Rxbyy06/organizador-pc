"""Lo que hay en disco: asignaturas, categorías y carpetas principales. Se lee cada vez."""
import os
import re
from dataclasses import dataclass

from .nombres import clave, sin_tildes

CATEGORIAS = ['1 - Teoría', '2 - Ejercicios', '3 - Seminarios', '4 - Prácticas', '5 - Exámenes', '6 - Otros']
TEORIA, EJERCICIOS, SEMINARIOS, PRACTICAS, EXAMENES, OTROS = CATEGORIAS

_ASIG = re.compile(r'^(\d)(r|n|t|º)?\s*-\s*T(\d)\s*-\s*(.+)$', re.I)
_CURSO = re.compile(r'^Curso (\d{4})-(\d{2})', re.I)
_PRINCIPAL = re.compile(r'^\d+ - ')


@dataclass
class Asignatura:
    ruta: str
    nombre: str          # «Sistemes Operatius»
    curso: int           # 1, 2…
    trimestre: int

    @property
    def carpeta(self) -> str:
        return os.path.basename(self.ruta)

    def base(self) -> str:
        """Donde van las categorías: la asignatura o su «Curso AAAA-AA» más reciente."""
        cursos = sorted((d for d in subcarpetas(self.ruta) if _CURSO.match(d)),
                        key=lambda d: _CURSO.match(d).groups())
        return os.path.join(self.ruta, cursos[-1]) if cursos else self.ruta

    def categoria(self, categoria: str) -> str:
        """Ruta de la categoría; si ya existe con otro número o tilde, esa."""
        base = self.base()
        buscada = _sin_numero(categoria)
        for d in subcarpetas(base):
            if _sin_numero(d) == buscada:
                return os.path.join(base, d)
        return os.path.join(base, categoria)


def _sin_numero(nombre: str) -> str:
    return sin_tildes(clave(re.sub(r'^\d+\s*-\s*', '', nombre)))


def subcarpetas(ruta: str) -> list[str]:
    try:
        with os.scandir(ruta) as it:
            return sorted(e.name for e in it if e.is_dir() and not e.name.startswith('.'))
    except OSError:
        return []


def asignaturas(ruta_uni: str) -> list[Asignatura]:
    res = []
    for d in subcarpetas(ruta_uni):
        if m := _ASIG.match(d):
            res.append(Asignatura(os.path.join(ruta_uni, d), m.group(4).strip(),
                                  int(m.group(1)), int(m.group(3))))
    return res


def asignatura_de(ruta: str, ruta_uni: str) -> Asignatura | None:
    """La asignatura que contiene esta ruta, si está dentro de la uni."""
    try:
        rel = os.path.relpath(ruta, ruta_uni)
    except ValueError:
        return None
    if rel.startswith('..') or rel == '.':
        return None
    primera = rel.split(os.sep)[0]
    if m := _ASIG.match(primera):
        return Asignatura(os.path.join(ruta_uni, primera), m.group(4).strip(), int(m.group(1)), int(m.group(3)))
    return None


def principales(onedrive: str) -> list[str]:
    return [d for d in subcarpetas(onedrive) if _PRINCIPAL.match(d)]


def existente_mas_profunda(ruta: str) -> str:
    while ruta and not os.path.isdir(ruta):
        padre = os.path.dirname(ruta)
        if padre == ruta:
            break
        ruta = padre
    return ruta
