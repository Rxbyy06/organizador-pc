"""Normas de nombres: saneado para OneDrive, NFC, longitud y utilidades de texto."""
import os
import re
import unicodedata

MAX_RUTA = 255
RESERVADOS = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)),
              *(f'LPT{i}' for i in range(1, 10))}


def nfc(s: str) -> str:
    return unicodedata.normalize('NFC', s)


def sin_tildes(s: str) -> str:
    s = unicodedata.normalize('NFD', s)
    return ''.join(c for c in s if not unicodedata.combining(c))


def clave(s: str) -> str:
    """Forma de comparar nombres: NFC, sin mayúsculas."""
    return nfc(s).casefold()


def sanear(nombre: str) -> str:
    """Un componente de ruta válido para OneDrive."""
    s = nfc(nombre)
    s = ''.join(c for c in s if unicodedata.category(c)[0] != 'C')
    s = re.sub(r'\s*:\s*', ' - ', s)
    s = s.replace('/', '-').replace('\\', '-').replace('|', '-').replace('"', "'")
    s = re.sub(r'[*?<>]', '', s)
    s = re.sub(r'\s+', ' ', s)
    s = re.sub(r'(\s*-\s*){2,}', ' - ', s)
    s = s.strip(' .-')
    if s.split('.')[0].upper() in RESERVADOS:
        s += '_'
    return s[:200].rstrip(' .') or 'Sin nombre'


def partir_ext(nombre: str) -> tuple[str, str]:
    base, ext = os.path.splitext(nombre)
    if not base:                     # «.gitignore»
        return nombre, ''
    return base, ext.lower()


_FECHA_HORA = re.compile(r'[_\s.-]*\d{1,2}[._-]\d{1,2}[._-]\d{2,4}(?:[._-]\d{1,2}){2,4}(?:[._-]\d{1,3})?(?!\d)')


def limpiar_original(base: str) -> str:
    """Hace legible un nombre de descarga: quita ids, marcas de tiempo y guiones bajos."""
    s = nfc(base)
    s = _FECHA_HORA.sub('', s)
    s = re.sub(r'^\d{3,}[_\s-]+', '', s)              # «1456_…»
    s = re.sub(r'\s*\((\d{1,2})\)$', '', s)            # «archivo (1)» de descargas repetidas
    s = re.sub(r'[_]+', ' ', s)
    s = re.sub(r'(?<=[a-z])(?=[A-Z][a-z])', ' ', s)    # camelCase
    s = re.sub(r'\s+', ' ', s).strip(' .-')
    return capitalizar(s)


def capitalizar(s: str) -> str:
    """«TEMA 3 INTEGRALS» → «Tema 3 integrals». Lo demás se deja como está."""
    letras = [c for c in s if c.isalpha()]
    if len(letras) > 4 and all(c.isupper() for c in letras):
        s = s.lower()
    return s[:1].upper() + s[1:]


def ruta_larga(p: str) -> str:
    """Prefijo \\\\?\\ para rutas de más de 240 caracteres (rutas largas desactivadas en Windows)."""
    if len(p) < 240 or p.startswith('\\\\?\\'):
        return p
    return '\\\\?\\' + os.path.abspath(p)


def recortar(carpeta: str, base: str, ext: str) -> str:
    """Acorta la base para que la ruta completa no pase de 255 caracteres."""
    sobra = len(os.path.join(carpeta, base + ext)) - MAX_RUTA
    if sobra > 0:
        base = base[:max(10, len(base) - sobra)].rstrip(' .-')
    return base


def libre(carpeta: str, base: str, ext: str, ocupados: set[str] | None = None) -> str:
    """Primer nombre «base», «base (2)»… que no exista en la carpeta."""
    ocupados = ocupados or set()
    n = 1
    while True:
        cand = base if n == 1 else f'{base} ({n})'
        if not os.path.exists(ruta_larga(os.path.join(carpeta, cand + ext))) \
                and clave(cand + ext) not in ocupados:
            return cand
        n += 1


def ruta_valida(ruta: str) -> str | None:
    """None si vale; si no, el motivo."""
    if len(ruta) > MAX_RUTA:
        return f'la ruta tiene {len(ruta)} caracteres (máximo {MAX_RUTA})'
    nombre = os.path.basename(ruta)
    if not nombre.strip(' .'):
        return 'el nombre está vacío'
    if re.search(r'["*:<>?/\\|]', nombre):
        return 'el nombre lleva caracteres no permitidos (" * : < > ? / \\ |)'
    if nombre != nombre.rstrip(' .'):
        return 'el nombre acaba en espacio o punto'
    if os.path.splitext(nombre)[0].upper() in RESERVADOS:
        return 'es un nombre reservado de Windows'
    return None
