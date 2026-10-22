"""Resumen semanal: qué ha hecho el programa, conflictos, duplicados nuevos, espacio y lo pendiente."""
import os
import sqlite3
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field

DIA = 86400


@dataclass
class Grupo:
    hash: str
    rutas: list[str]              # absolutas
    casi: bool = False            # mismo texto, distinto archivo (DUDOSO)


@dataclass
class DatosResumen:
    desde: float
    pasadas: int = 0
    copiados: Counter = field(default_factory=Counter)
    movidos: Counter = field(default_factory=Counter)
    a_papelera: int = 0
    conflictos: list[str] = field(default_factory=list)
    errores: Counter = field(default_factory=Counter)        # mensaje → veces
    words: Counter = field(default_factory=Counter)          # nuevos, actualizados, editados, a_papelera
    acciones: Counter = field(default_factory=Counter)       # tipo de acción del historial → cuántas
    duplicados: list[Grupo] = field(default_factory=list)
    espacio: list = field(default_factory=list)              # espacio.Uso
    pendientes: list[str] = field(default_factory=list)
    capturas: int = 0

    @property
    def notable(self) -> bool:
        """¿Merece abrir la ventana? Si no, basta con una notificación de «semana sin novedades»."""
        return bool(self.conflictos or self.duplicados or self.capturas or any(u.aviso for u in self.espacio)
                    or self.pendientes or any(n >= 3 for n in self.errores.values()) or self.words['editados'])


class Resumen:
    def __init__(self, cfg, historial, ahora=time.time):
        self.cfg, self.historial, self.ahora = cfg, historial, ahora

    # Duplicados
    def duplicados(self, solo_nuevos: bool = True) -> list[Grupo]:
        """Idénticos (y casi idénticos) dentro de las carpetas, sin contar los de dentro de repos de código."""
        vistos = self.historial.duplicados_vistos()
        db = sqlite3.connect(os.path.join(self.cfg.datos, 'indice.sqlite'))
        try:
            iguales, casi = defaultdict(list), defaultdict(list)
            for ruta, h, th, tam in db.execute('SELECT ruta, hash, texto_hash, tam FROM archivos '
                                               'WHERE hash IS NOT NULL AND tam > 0 AND privado = 0'):
                iguales[h].append(ruta)
                if th:
                    casi[th].append((ruta, h))
        finally:
            db.close()
        repos: dict[str, bool] = {}

        def en_repo(rel):
            partes = rel.split(os.sep)
            for i in range(len(partes) - 1, 0, -1):
                d = os.sep.join(partes[:i])
                if d not in repos:
                    repos[d] = os.path.isdir(os.path.join(self.cfg.onedrive, d, '.git'))
                if repos[d]:
                    return True
            return False
        res = []
        for h, rutas in iguales.items():
            rutas = [r for r in rutas if not en_repo(r)]
            if len(rutas) > 1 and vistos.get(h) != 'ignorar' and not (solo_nuevos and h in vistos):
                res.append(Grupo(h, [os.path.join(self.cfg.onedrive, r) for r in sorted(rutas)]))
        for th, lista in casi.items():
            lista = [(r, h) for r, h in lista if not en_repo(r)]
            if len({h for _, h in lista}) > 1 and vistos.get('t' + th) != 'ignorar' \
                    and not (solo_nuevos and 't' + th in vistos):
                res.append(Grupo('t' + th, [os.path.join(self.cfg.onedrive, r) for r, _ in sorted(lista)], casi=True))
        return res

    def datos(self, pendientes: list[str], capturas: int, espacio: list) -> DatosResumen:
        desde = self.historial.leer_estado('ultimo_resumen') or (self.ahora() - 7 * DIA)
        d = DatosResumen(desde, espacio=espacio, pendientes=pendientes, capturas=capturas)
        for _, tipo, s in self.historial.stats_desde(desde):
            if tipo == 'sincro':
                d.pasadas += 1
                d.copiados.update(s.get('copiados', {}))
                d.movidos.update(s.get('movidos', {}))
                d.a_papelera += s.get('a_papelera', 0)
                d.conflictos += s.get('conflictos', [])
                d.errores.update(s.get('errores', []))
            elif tipo == 'docs':
                d.words.update({k: len(v) for k, v in s.items() if isinstance(v, list)})
        for tipo, estado, _ in self.historial.acciones_desde(desde):
            if estado == 'hecho':
                d.acciones[tipo] += 1
        d.duplicados = self.duplicados()
        return d

    def hecho(self, d: DatosResumen) -> None:
        """Lo enseñado ya no vuelve a salir como «nuevo»."""
        self.historial.marcar_duplicados([g.hash for g in d.duplicados], 'mostrado')
        self.historial.poner_estado('ultimo_resumen', self.ahora())

    def ignorar(self, g: Grupo) -> None:
        self.historial.marcar_duplicados([g.hash], 'ignorar')
