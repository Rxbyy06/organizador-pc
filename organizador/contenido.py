"""Título, primeras líneas y texto de un documento (PDF, Word, PowerPoint)."""
import hashlib
import re
import zipfile
from dataclasses import dataclass, field
from html import unescape

from .nombres import nfc, ruta_larga, sin_tildes

_BASURA_TITULO = re.compile(
    r'^(microsoft (word|powerpoint)|untitled|sin t[ií]tulo|presentaci[oó]n de powerpoint|'
    r'diapositiva|document|documento|slide|pdf|title|t[ií]tulo|\d+)\b|\.(docx?|pptx?|tex|dvi|pdf)$', re.I)
_CABECERA = re.compile(
    r'universitat pompeu fabra|\bupf\b|escola d.enginyeria|grau en|grado en|curs \d{4}|'
    r'curso \d{4}|^p[àa]gina|^page \d|^\d+$|^\d{1,2}/\d{1,2}/\d{2,4}$', re.I)


@dataclass
class Contenido:
    titulos: list[str] = field(default_factory=list)   # candidatos, del más probable al menos
    lineas: list[str] = field(default_factory=list)
    texto: str = ''               # primeras páginas, para clasificar
    texto_hash: str | None = None  # huella del texto entero (PDF «casi idénticos»)
    paginas: int = 0
    creado: tuple[int, int] | None = None   # (año, mes) de creación del PDF

    @property
    def titulo(self) -> str:
        return self.titulos[0] if self.titulos else ''


_ACENTOS = {'´': '́', "'": '́', '`': '̀', '¨': '̈', '^': '̂', '~': '̃'}


def reparar(t: str) -> str:
    """Arregla el texto típico de PDF hechos con LaTeX: «N´umeros», «C ` ALCUL», «V ECTOR S PACES»."""
    t = t.replace('ı', 'i').replace('​', '')
    t = re.sub(r'\s?([´`¨^~])\s?([A-Za-z])', lambda m: m.group(2) + _ACENTOS[m.group(1)], t)
    t = re.sub(r'([A-Za-z])\s?([´¨])', lambda m: m.group(1) + _ACENTOS[m.group(2)], t)
    versalitas = re.compile(r'\b([A-Z]) ([A-Z̀-ͯ]{2,})\b')
    t = nfc(t)
    if len(versalitas.findall(t)) >= 2:
        t = versalitas.sub(r'\1\2', t)
    else:   # una sola vez: «S EMINAR» sí, pero «ÀLGEBRA I ESTADÍSTICA» no
        t = re.sub(r'\b([B-DF-HJ-NP-TV-XZ]) ([A-Z̀-ͯ]{2,})\b', r'\1\2', t)
    # «FíSICA»: la letra acentuada de LaTeX sale en minúscula en medio de mayúsculas.
    t = re.sub(r'(?<=[A-Z])([a-zà-ÿ])(?=[A-Z]{2})', lambda m: m.group(1).upper(), t)
    t = t.replace('ﬁ', 'fi').replace('ﬂ', 'fl').replace('’', "'")
    return nfc(re.sub(r'\s+', ' ', t)).strip()


def _titulo_valido(t: str) -> bool:
    t = t.strip()
    return 3 <= len(t) <= 120 and not _BASURA_TITULO.search(t) and not _CABECERA.search(t)


def huella_texto(texto: str) -> str | None:
    t = re.sub(r'[\W_]+', '', sin_tildes(nfc(texto)).casefold())
    if len(t) < 200:           # PDF escaneado o casi vacío: no sirve para comparar
        return None
    return hashlib.blake2b(t.encode(), digest_size=16).hexdigest()


def _pdf(ruta: str, completo: bool) -> Contenido:
    import pymupdf
    pymupdf.TOOLS.mupdf_display_errors(False)
    c = Contenido()
    with pymupdf.open(ruta_larga(ruta)) as doc:
        if doc.needs_pass:
            return c
        c.paginas = doc.page_count
        if doc.page_count == 0:
            return c
        # Título: el texto de letra más grande de la primera página.
        tramos = []
        for bloque in doc[0].get_text('dict').get('blocks', []):
            for linea in bloque.get('lines', []):
                texto = ' '.join(s['text'] for s in linea['spans']).strip()
                if texto:
                    tamano = max(s['size'] for s in linea['spans'])
                    tramos.append((round(tamano, 1), linea['bbox'][1], texto))
        for tamano in sorted({t[0] for t in tramos}, reverse=True)[:4]:
            lineas = [t for t in sorted(tramos, key=lambda t: t[1])
                      if abs(t[0] - tamano) <= 0.5 and not _CABECERA.search(t[2])]
            partes = lineas[:1]
            for t in lineas[1:3]:            # solo las líneas pegadas: el autor suele ir aparte
                if t[1] - partes[-1][1] > tamano * 1.6:
                    break
                partes.append(t)
            cand = reparar(' '.join(p[2] for p in partes))
            if _titulo_valido(cand) and cand not in c.titulos:
                c.titulos.append(cand)
        if m := re.match(r'D:(\d{4})(\d{2})', (doc.metadata or {}).get('creationDate') or ''):
            if 2000 < int(m.group(1)) < 2100 and 1 <= int(m.group(2)) <= 12:
                c.creado = (int(m.group(1)), int(m.group(2)))
        meta = reparar((doc.metadata or {}).get('title') or '')
        if _titulo_valido(meta) and meta not in c.titulos:
            c.titulos.append(meta)
        primeras = ''.join(doc[i].get_text() for i in range(min(3, doc.page_count)))
        c.lineas = [reparar(l) for l in primeras.splitlines() if l.strip()][:20]
        c.texto = primeras[:20000]
        if completo:
            todo = primeras + ''.join(doc[i].get_text() for i in range(3, min(doc.page_count, 300)))
            c.texto_hash = huella_texto(todo)
    return c


def _office(ruta: str) -> Contenido:
    c = Contenido()
    with zipfile.ZipFile(ruta_larga(ruta)) as z:
        nombres = set(z.namelist())
        if 'docProps/core.xml' in nombres:
            core = z.read('docProps/core.xml').decode('utf-8', 'replace')
            if m := re.search(r'<dc:title>(.*?)</dc:title>', core, re.S):
                if _titulo_valido(unescape(m.group(1))):
                    c.titulos.append(unescape(m.group(1)).strip())
        xml = ''
        if 'word/document.xml' in nombres:
            xml = z.read('word/document.xml').decode('utf-8', 'replace')
            parrafos = re.findall(r'<w:p[ >].*?</w:p>', xml, re.S)
            textos = [''.join(re.findall(r'<w:t[^>]*>(.*?)</w:t>', p)) for p in parrafos]
        else:
            diapos = sorted(n for n in nombres if re.match(r'ppt/slides/slide\d+\.xml$', n))
            textos = []
            for n in diapos[:3]:
                textos += re.findall(r'<a:t>(.*?)</a:t>', z.read(n).decode('utf-8', 'replace'))
        textos = [unescape(t).strip() for t in textos if t.strip()]
        c.lineas = textos[:20]
        c.texto = '\n'.join(textos)[:20000]
        c.titulos += [t for t in textos[:3] if _titulo_valido(t) and t not in c.titulos]
    return c


def analizar(ruta: str, completo: bool = True) -> Contenido:
    """Nunca falla: si no se puede leer, devuelve un Contenido vacío."""
    ext = ruta.lower().rsplit('.', 1)[-1]
    try:
        if ext == 'pdf':
            return _pdf(ruta, completo)
        if ext in ('docx', 'pptx'):
            return _office(ruta)
    except Exception:
        pass
    return Contenido()
