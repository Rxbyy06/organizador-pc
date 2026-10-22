"""Copias en Word de los Google Docs: del manifiesto de cada cuenta a OneDrive.

El script de cada cuenta (apps_script/exportar_docs.gs) deja en «Mi unidad/_exportados_docs» un .docx por
Doc y un manifest.json. Aquí, antes de cada pasada de sincronización:
  - cada Word se coloca en OneDrive, en la misma carpeta que su Doc y con el mismo nombre, en solo lectura;
  - si el Doc cambia, se actualiza; si se renombra o se mueve, el Word también; si se borra, el Word va a la papelera;
  - si alguien editó el Word, no se pisa: se aparta como «Nombre (editado en Word AAAA-MM-DD).docx»;
  - el sincronizador nunca sube ese Word a la copia de su cuenta (en G: solo se ve el Doc).
También detecta un PDF que parece la versión definitiva de un Doc, para preguntar si se borra el Doc.
"""
import datetime
import json
import logging
import os
import re
import shutil
import sqlite3
import stat
import threading
import time
from dataclasses import dataclass, field

from . import contenido, papelera
from .huellas import huella
from .nombres import clave, libre, nfc, partir_ext, recortar, ruta_larga, sanear

log = logging.getLogger(__name__)
TMP = '.orgdocs-tmp'


@dataclass
class InformeDocs:
    nuevos: list[str] = field(default_factory=list)
    actualizados: list[str] = field(default_factory=list)
    movidos: list[str] = field(default_factory=list)
    a_papelera: list[str] = field(default_factory=list)
    editados: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    pasos: list[dict] = field(default_factory=list)
    pdf_definitivos: list[tuple[str, str, str]] = field(default_factory=list)   # (ruta del PDF, id del Doc, nombre)

    @property
    def hubo_cambios(self) -> bool:
        return bool(self.nuevos or self.actualizados or self.movidos or self.a_papelera or self.editados)

    def resumen(self) -> str:
        partes = []
        for n, texto in ((self.nuevos, 'nuevo'), (self.actualizados, 'actualizado'), (self.movidos, 'movido o renombrado'),
                         (self.a_papelera, 'a la papelera (su Doc ya no está)')):
            if n:
                partes.append(f'{len(n)} Word {texto}')
        if self.editados:
            partes.append(f'{len(self.editados)} editado(s) a mano y apartado(s)')
        return '; '.join(partes) or 'sin cambios'


def _escribible(ruta: str) -> None:
    try:
        os.chmod(ruta_larga(ruta), stat.S_IWRITE | stat.S_IREAD)
    except OSError:
        pass


def _solo_lectura(ruta: str) -> None:
    try:
        os.chmod(ruta_larga(ruta), stat.S_IREAD)
    except OSError:
        pass


def _palabras(texto: str) -> set[str]:
    return set(re.findall(r'\w{4,}', nfc(texto).lower()))


class Words:
    def __init__(self, cfg, indice=None, ahora=time.time):
        self.cfg, self.indice, self.ahora = cfg, indice, ahora
        self._lock = threading.Lock()
        self.db = sqlite3.connect(os.path.join(cfg.datos, 'docs.sqlite'), check_same_thread=False)
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS words (id TEXT PRIMARY KEY, copia TEXT, nombre TEXT, ruta_doc TEXT,
                                              rel TEXT, exportado TEXT, hash TEXT);
            CREATE TABLE IF NOT EXISTS pdfs (rel TEXT PRIMARY KEY, mtime REAL, decision TEXT, doc TEXT);
        ''')

    # ── Para el sincronizador ───────────────────────────────────────────────
    def excluidas(self) -> dict[str, set[str]]:
        """Claves de los Word que no deben ir a la copia de su cuenta: {copia: {clave}}."""
        res: dict[str, set[str]] = {}
        with self._lock:
            for copia, rel in self.db.execute('SELECT copia, rel FROM words'):
                res.setdefault(copia, set()).add(clave(rel))
        return res

    def filas(self) -> list[tuple]:
        with self._lock:
            return self.db.execute('SELECT id, copia, nombre, ruta_doc, rel, exportado, hash FROM words').fetchall()

    # ── Pasada ──────────────────────────────────────────────────────────────
    def actualizar(self) -> InformeDocs:
        inf = InformeDocs()
        with self._lock:
            for cuenta in self.cfg.cuentas_docs:
                try:
                    self._cuenta(cuenta, inf)
                except Exception as e:
                    log.exception('Copias Word de %s', cuenta['copia'])
                    inf.avisos.append(f'Copias Word de {cuenta["copia"]}: {e}')
            self.db.commit()
        try:
            self._buscar_pdfs(inf)
        except Exception:
            log.exception('Buscando PDF definitivos')
        return inf

    def _cuenta(self, cuenta: dict, inf: InformeDocs) -> None:
        copia, carpeta = cuenta['copia'], cuenta['exportados']
        manifiesto = os.path.join(carpeta, 'manifest.json')
        if not os.path.isfile(manifiesto):
            return                                     # el script aún no se ha instalado, o Drive no está
        with open(manifiesto, encoding='utf-8') as f:
            docs = json.load(f).get('docs', {})
        filas = {r[0]: r for r in self.db.execute(
            'SELECT id, copia, nombre, ruta_doc, rel, exportado, hash FROM words WHERE copia=?', (copia,))}
        ocupadas = {clave(rel) for (rel,) in self.db.execute('SELECT rel FROM words')}

        for id_, d in docs.items():
            origen = os.path.join(carpeta, id_ + '.docx')
            rel = self._destino(d, ocupadas - ({clave(filas[id_][4])} if id_ in filas else set()))
            fila = filas.get(id_)
            if fila is None:
                if not os.path.isfile(origen):
                    continue                           # el .docx aún no ha bajado
                h = self._copiar(origen, rel)
                self.db.execute('INSERT INTO words VALUES (?,?,?,?,?,?,?)',
                                (id_, copia, d['nombre'], d['ruta'], rel, d.get('exportado'), h))
                ocupadas.add(clave(rel))
                inf.nuevos.append(rel)
                continue
            _, _, _, _, rel_viejo, exportado, h_viejo = fila
            actual = os.path.join(self.cfg.onedrive, rel_viejo)
            if rel != rel_viejo and os.path.exists(ruta_larga(actual)):       # Doc renombrado o movido
                destino = os.path.join(self.cfg.onedrive, rel)
                os.makedirs(ruta_larga(os.path.dirname(destino)), exist_ok=True)
                os.rename(ruta_larga(actual), ruta_larga(destino))
                if self.indice is not None:
                    self.indice.quitar(actual)
                    self.indice.anadir(destino, h_viejo)
                inf.movidos.append(f'{rel_viejo} → {rel}')
            ocupadas.discard(clave(rel_viejo))
            ocupadas.add(clave(rel))
            destino = os.path.join(self.cfg.onedrive, rel)
            falta = not os.path.exists(ruta_larga(destino))
            if (d.get('exportado') != exportado or falta) and os.path.isfile(origen):
                if not falta and self._huella(destino) != h_viejo:            # alguien lo editó: apartarlo
                    self._apartar_editado(destino, inf)
                h = self._copiar(origen, rel)
                (inf.nuevos if falta and d.get('exportado') == exportado else inf.actualizados).append(rel)
                exportado, h_viejo = d.get('exportado'), h
            self.db.execute('UPDATE words SET nombre=?, ruta_doc=?, rel=?, exportado=?, hash=? WHERE id=?',
                            (d['nombre'], d['ruta'], rel, exportado, h_viejo, id_))

        quitar = [id_ for id_ in filas if id_ not in docs]
        if len(quitar) > self.cfg.max_borrados:
            inf.avisos.append(f'{copia}: han desaparecido {len(quitar)} Docs de golpe; no toco sus Word hasta que lo mires')
            return
        for id_ in quitar:
            rel = filas[id_][4]
            ruta = os.path.join(self.cfg.onedrive, rel)
            if os.path.exists(ruta_larga(ruta)):
                if self._huella(ruta) != filas[id_][6]:
                    self._apartar_editado(ruta, inf)              # lo editado a mano se queda, apartado
                else:
                    _escribible(ruta)
                    fecha = papelera.enviar(ruta)
                    inf.pasos.append({'op': 'papelera', 'ruta': ruta, 'fecha': fecha})
                    if self.indice is not None:
                        self.indice.quitar(ruta)
                    inf.a_papelera.append(rel)
            self.db.execute('DELETE FROM words WHERE id=?', (id_,))

    def _destino(self, d: dict, ocupadas: set[str]) -> str:
        """Ruta en OneDrive del Word: la carpeta del Doc y su nombre (con «(Doc)» si choca con otro archivo)."""
        carpeta = os.path.join(*[sanear(p) for p in d['ruta'].split('/') if p])
        base = sanear(d['nombre'])
        base = recortar(os.path.join(self.cfg.onedrive, carpeta), base, '.docx')
        rel = os.path.join(carpeta, base + '.docx')
        ajeno = os.path.exists(ruta_larga(os.path.join(self.cfg.onedrive, rel))) and clave(rel) not in \
            {clave(r) for (r,) in self.db.execute('SELECT rel FROM words')}
        if ajeno or clave(rel) in ocupadas:
            rel = os.path.join(carpeta, base + ' (Doc).docx')
        return rel

    def _huella(self, ruta: str) -> str | None:
        try:
            return huella(ruta)
        except OSError:
            return None

    def _copiar(self, origen: str, rel: str) -> str:
        destino = os.path.join(self.cfg.onedrive, rel)
        os.makedirs(ruta_larga(os.path.dirname(destino)), exist_ok=True)
        tmp = destino + TMP
        shutil.copyfile(ruta_larga(origen), ruta_larga(tmp))
        if os.path.exists(ruta_larga(destino)):
            _escribible(destino)
        os.replace(ruta_larga(tmp), ruta_larga(destino))
        _solo_lectura(destino)
        h = huella(destino)
        if self.indice is not None:
            self.indice.anadir(destino, h)
        return h

    def _apartar_editado(self, ruta: str, inf: InformeDocs) -> None:
        carpeta = os.path.dirname(ruta)
        base, ext = partir_ext(os.path.basename(ruta))
        hoy = datetime.date.fromtimestamp(self.ahora()).isoformat()
        nuevo = libre(carpeta, f'{base} (editado en Word {hoy})', ext)
        _escribible(ruta)
        os.rename(ruta_larga(ruta), ruta_larga(os.path.join(carpeta, nuevo + ext)))
        inf.editados.append(os.path.join(os.path.relpath(carpeta, self.cfg.onedrive), nuevo + ext))

    # ── PDF definitivo ──────────────────────────────────────────────────────
    def _buscar_pdfs(self, inf: InformeDocs) -> None:
        """PDF en la carpeta de un Doc con su mismo nombre o su mismo texto: hay que preguntar."""
        por_carpeta: dict[str, list[tuple]] = {}
        for fila in self.filas():
            por_carpeta.setdefault(os.path.dirname(fila[4]), []).append(fila)
        with self._lock:
            vistos = {r: (m, dec) for r, m, dec in self.db.execute('SELECT rel, mtime, decision FROM pdfs')}
        for carpeta, filas in por_carpeta.items():
            try:
                nombres = os.listdir(ruta_larga(os.path.join(self.cfg.onedrive, carpeta)))
            except OSError:
                continue
            for n in nombres:
                if not n.lower().endswith('.pdf'):
                    continue
                rel = os.path.join(carpeta, n)
                ruta = os.path.join(self.cfg.onedrive, rel)
                mtime = os.path.getmtime(ruta_larga(ruta))
                previo = vistos.get(rel)
                if previo and (previo[1] in ('conservar', 'borrado') or previo[0] == mtime):
                    if previo[1] == 'pendiente':
                        doc = self._doc_de(rel, filas)
                        if doc:
                            inf.pdf_definitivos.append((ruta, doc[0], doc[2]))
                    continue
                doc = self._doc_de(rel, filas)
                with self._lock, self.db:
                    self.db.execute('INSERT OR REPLACE INTO pdfs VALUES (?,?,?,?)',
                                    (rel, mtime, 'pendiente' if doc else 'distinto', doc[0] if doc else None))
                if doc:
                    inf.pdf_definitivos.append((ruta, doc[0], doc[2]))

    def _doc_de(self, rel_pdf: str, filas: list[tuple]):
        base = clave(partir_ext(os.path.basename(rel_pdf))[0])
        for f in filas:
            if clave(partir_ext(os.path.basename(f[4]))[0]) in (base, base + ' (doc)') or clave(f[2]) == base:
                return f
        texto_pdf = _palabras(contenido.analizar(os.path.join(self.cfg.onedrive, rel_pdf), completo=False).texto)
        if len(texto_pdf) < 30:
            return None
        for f in filas:
            texto_doc = _palabras(contenido.analizar(os.path.join(self.cfg.onedrive, f[4])).texto)
            if texto_doc and len(texto_pdf & texto_doc) / len(texto_pdf | texto_doc) >= 0.8:
                return f
        return None

    def decidir_pdf(self, ruta_pdf: str, decision: str) -> None:
        rel = os.path.relpath(ruta_pdf, self.cfg.onedrive)
        with self._lock, self.db:
            self.db.execute('UPDATE pdfs SET decision=? WHERE rel=?', (decision, rel))

    def borrar_doc(self, id_: str) -> str:
        """Manda el Doc a la papelera de Drive borrando su .gdoc en la copia de su cuenta. Devuelve la ruta."""
        with self._lock:
            f = self.db.execute('SELECT copia, nombre, ruta_doc FROM words WHERE id=?', (id_,)).fetchone()
        if not f:
            raise FileNotFoundError('ese Doc ya no está')
        copia, nombre, ruta_doc = f
        raiz = next(c['raiz'] for c in self.cfg.copias if c['nombre'] == copia)
        carpeta = os.path.join(raiz, *ruta_doc.split('/'))
        candidatos = [n for n in os.listdir(carpeta) if n.lower().endswith('.gdoc')
                      and clave(partir_ext(n)[0]) in (clave(nombre), clave(sanear(nombre)))]
        if not candidatos:
            raise FileNotFoundError(f'no encuentro «{nombre}.gdoc» en {carpeta}')
        ruta = os.path.join(carpeta, candidatos[0])
        papelera.enviar(ruta)
        return ruta
