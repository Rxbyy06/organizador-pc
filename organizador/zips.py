"""Mirar dentro de un ZIP y descomprimirlo con nombres válidos (NFC, sin caracteres prohibidos)."""
import os
import zipfile
from dataclasses import dataclass, field

from .nombres import nfc, ruta_larga, sanear

BASURA = {'__macosx', '.ds_store', 'thumbs.db', 'desktop.ini'}
CODIGO = {'.c', '.h', '.cpp', '.hpp', '.cc', '.java', '.py', '.ipynb', '.js', '.ts', '.rs', '.go',
          '.hs', '.m', '.sh', '.s', '.asm', '.kt', '.cs', '.sql', '.r', '.jl'}
MAXIMO = 4 << 30


@dataclass
class InfoZip:
    miembros: list[tuple[zipfile.ZipInfo, str]] = field(default_factory=list)   # (entrada, ruta saneada)
    raiz_unica: str | None = None
    archivo_unico: bool = False
    tam: int = 0
    tiene_codigo: bool = False
    error: str | None = None

    @property
    def total(self) -> int:
        return len(self.miembros)


def _nombre(info: zipfile.ZipInfo) -> str:
    n = info.filename
    if not info.flag_bits & 0x800:           # sin marca UTF-8: zipfile lo leyó como cp437
        crudo = n.encode('cp437', 'replace')
        for cod in ('utf-8', 'cp850'):
            try:
                n = crudo.decode(cod)
                break
            except UnicodeDecodeError:
                pass
    return nfc(n)


def analizar(ruta: str) -> InfoZip:
    z = InfoZip()
    try:
        with zipfile.ZipFile(ruta_larga(ruta)) as f:
            for info in f.infolist():
                if info.is_dir():
                    continue
                partes = [p for p in _nombre(info).replace('\\', '/').split('/') if p not in ('', '.')]
                if not partes or '..' in partes or any(p.lower() in BASURA for p in partes):
                    continue
                z.miembros.append((info, os.path.join(*[sanear(p) for p in partes])))
                z.tam += info.file_size
                z.tiene_codigo |= os.path.splitext(partes[-1])[1].lower() in CODIGO
    except (zipfile.BadZipFile, OSError, NotImplementedError) as e:
        z.error = f'no se puede abrir el ZIP ({e})'
        return z
    if not z.miembros:
        z.error = 'el ZIP está vacío'
    elif z.tam > MAXIMO:
        z.error = 'el ZIP descomprimido ocuparía más de 4 GB'
    primeros = {m[1].split(os.sep)[0] for m in z.miembros}
    if len(z.miembros) == 1 and os.sep not in z.miembros[0][1]:
        z.archivo_unico = True
    elif len(primeros) == 1:
        z.raiz_unica = primeros.pop()
    return z


def destinos(z: InfoZip, carpeta: str, nombre: str) -> list[tuple[zipfile.ZipInfo, str]]:
    """Dónde acaba cada archivo. «nombre» es la carpeta nueva (o el archivo, si solo hay uno)."""
    if z.archivo_unico:
        info, rel = z.miembros[0]
        return [(info, os.path.join(carpeta, nombre + os.path.splitext(rel)[1]))]
    res = []
    for info, rel in z.miembros:
        if z.raiz_unica:
            rel = rel.split(os.sep, 1)[1] if os.sep in rel else rel
        res.append((info, os.path.join(carpeta, nombre, rel)))
    return res


def extraer(ruta_zip: str, info: zipfile.ZipInfo, destino: str) -> None:
    os.makedirs(ruta_larga(os.path.dirname(destino)), exist_ok=True)
    with zipfile.ZipFile(ruta_larga(ruta_zip)) as f, f.open(info) as src, \
            open(ruta_larga(destino), 'xb') as dst:
        while bloque := src.read(1 << 20):
            dst.write(bloque)
