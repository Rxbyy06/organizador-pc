"""Parecido de un documento con cada carpeta (TF-IDF sobre nombres y textos que ya tienes)."""
import math
import os
import re
import time
from collections import Counter, defaultdict

from .carpetas import CATEGORIAS, _sin_numero
from .nombres import sin_tildes

STOP = set("""
del les els las los una uno unos unas que per por para con como amb sense sin sobre entre sus seu seva
seus seves this that the and for with from are was were has have not but you your our its into than
pdf doc docx pptx png jpg jpeg zip copia copy final versio version nou nuevo nueva new est son molt muy
mas mes pero cada aquest aquesta este esta esto aixo cual qual quan cuando donde on fins hasta tambien tambe
ser estar haber hacer fer pot puede poden pueden dels pel pels has han hem hemos tenim tenemos
upf universitat universidad pompeu fabra curs curso grau grado escola enginyeria ingenieria
tema temes teoria seminari seminaris seminario seminarios practica practiques practicas examen examens
examenes exam exercicis ejercicios solucions soluciones solution solutions enunciat enunciado entrega
sesion sessio session clase classe parcial pagina page
""".split())


def tokenizar(texto: str, maximo: int | None = None) -> list[str]:
    vistos = dict.fromkeys(t for t in re.findall(r'[a-z]{3,20}', sin_tildes(texto).lower()) if t not in STOP)
    lista = list(vistos)
    return lista[:maximo] if maximo else lista


def clase_de(rel: str) -> tuple[str, str | None]:
    """(carpeta-clase, categoría) de un archivo: «principal\\sub» y, en la uni, su categoría."""
    partes = rel.split(os.sep)
    if len(partes) < 2:
        return partes[0], None
    if len(partes) == 2:
        return partes[0], None
    clase = os.path.join(partes[0], partes[1])
    cats = {_sin_numero(c): c for c in CATEGORIAS}
    for p in partes[2:-1]:
        if _sin_numero(p) in cats:
            return clase, cats[_sin_numero(p)]
    return clase, None


class Perfil:
    def __init__(self):
        self.vectores: dict[str, dict[str, float]] = {}
        self.categorias: dict[tuple[str, str], dict[str, float]] = {}
        self.idf: dict[str, float] = {}
        self.recientes: set[str] = set()
        self.listo = False

    def construir(self, filas) -> None:
        """filas: (ruta relativa, palabras, mtime)."""
        cuentas: dict[str, Counter] = defaultdict(Counter)
        cuentas_cat: dict[tuple[str, str], Counter] = defaultdict(Counter)
        df, n_docs, ultimo = Counter(), 0, defaultdict(float)
        for rel, palabras, mtime in filas:
            clase, cat = clase_de(rel)
            carpetas_intermedias = ' '.join(rel.split(os.sep)[2:-1])
            toks = set(tokenizar(f'{os.path.splitext(os.path.basename(rel))[0]} {carpetas_intermedias} '
                                 f'{palabras or ""}'))
            if not toks:
                continue
            n_docs += 1
            df.update(toks)
            cuentas[clase].update(toks)
            if cat:
                cuentas_cat[(clase, cat)].update(toks)
            ultimo[clase] = max(ultimo[clase], mtime or 0)
        idf = {t: math.log((n_docs + 1) / (n + 1)) + 1 for t, n in df.items()}

        def vector(c: Counter) -> dict[str, float]:
            v = {t: (1 + math.log(n)) * idf[t] for t, n in c.items()}
            norma = math.sqrt(sum(x * x for x in v.values())) or 1
            return {t: x / norma for t, x in v.items()}

        self.idf = idf
        self.vectores = {c: vector(v) for c, v in cuentas.items()}
        self.categorias = {k: vector(v) for k, v in cuentas_cat.items()}
        hace = time.time() - 120 * 86400
        self.recientes = {c for c, m in ultimo.items() if m > hace}
        self.listo = True

    def _doc(self, tokens: list[str]) -> dict[str, float]:
        v = {t: self.idf[t] for t in set(tokens) if t in self.idf}
        norma = math.sqrt(sum(x * x for x in v.values())) or 1
        return {t: x / norma for t, x in v.items()}

    @staticmethod
    def _coseno(a: dict[str, float], b: dict[str, float]) -> float:
        if len(a) > len(b):
            a, b = b, a
        return sum(x * b.get(t, 0) for t, x in a.items())

    def clasificar(self, tokens: list[str], prefijo: str = '') -> list[tuple[str, float]]:
        """Carpetas ordenadas por parecido. «prefijo» limita a las de dentro de una carpeta."""
        d = self._doc(tokens)
        if not d:
            return []
        res = []
        for clase, v in self.vectores.items():
            if prefijo and not clase.startswith(prefijo + os.sep):
                continue
            p = self._coseno(d, v)
            if clase in self.recientes:
                p *= 1.15
            res.append((clase, p))
        return sorted(res, key=lambda x: -x[1])

    def tipicas(self, clase: str, n: int = 12) -> set[str]:
        """Las palabras que más distinguen una carpeta (en la uni, el nombre de la asignatura en inglés…)."""
        v = self.vectores.get(clase, {})
        return set(sorted(v, key=v.get, reverse=True)[:n])

    def categoria(self, clase: str, tokens: list[str]) -> str | None:
        d = self._doc(tokens)
        mejores = sorted(((self._coseno(d, v), cat) for (c, cat), v in self.categorias.items() if c == clase),
                         reverse=True)
        return mejores[0][1] if mejores and mejores[0][0] > 0.05 else None
