"""Papelera de reciclaje: enviar (send2trash) y recuperar (para «Deshacer»).

Para recuperar se leen los archivos $I de C:\\$Recycle.Bin\\<usuario>, que guardan la ruta
original y la fecha de borrado; el contenido está en el $R del mismo nombre.
"""
import datetime
import os
import shutil
import struct
import time

from send2trash import send2trash

from .nombres import nfc, partir_ext, ruta_larga

_SID = None


def enviar(ruta: str) -> float:
    """A la Papelera. Si no cabe en ella, Windows lo borraría definitivamente sin avisar: entonces no se toca."""
    ruta = os.path.normpath(os.path.abspath(ruta))           # el Shell no admite «/» mezcladas
    capacidad = capacidad_papelera(ruta)
    if capacidad is not None:
        tam = _tamano(ruta)
        if tam > capacidad * 0.9:
            raise OSError(f'«{os.path.basename(ruta)}» ({tam / 2**20:.0f} MB) no cabe en la Papelera de esa unidad '
                          f'({capacidad / 2**20:.0f} MB): Windows lo borraría para siempre, así que no lo toco')
    send2trash(ruta)
    return time.time()


def _tamano(ruta: str) -> int:
    if os.path.isfile(ruta_larga(ruta)):
        return os.path.getsize(ruta_larga(ruta))
    total = 0
    for r, _, fs in os.walk(ruta_larga(ruta)):
        for f in fs:
            try:
                total += os.path.getsize(os.path.join(r, f))
            except OSError:
                pass
    return total


def capacidad_papelera(ruta: str) -> int | None:
    """Tamaño máximo (bytes) de la Papelera de la unidad de esa ruta, según la configuración de Windows."""
    import ctypes
    import winreg
    unidad = os.path.splitdrive(ruta)[0] + os.sep
    buf = ctypes.create_unicode_buffer(100)
    if not ctypes.windll.kernel32.GetVolumeNameForVolumeMountPointW(unidad, buf, 100):
        return None
    guid = buf.value[buf.value.find('{'):buf.value.find('}') + 1]
    try:
        clave = r'Software\Microsoft\Windows\CurrentVersion\Explorer\BitBucket\Volume' + '\\' + guid
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, clave) as k:
            if winreg.QueryValueEx(k, 'NukeOnDelete')[0]:
                return 0                                    # esa unidad borra sin pasar por la Papelera
            return int(winreg.QueryValueEx(k, 'MaxCapacity')[0]) << 20
    except OSError:
        return None


def _sid() -> str:
    global _SID
    if _SID is None:
        import win32api
        import win32security
        tok = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32security.TOKEN_QUERY)
        _SID = win32security.ConvertSidToStringSid(win32security.GetTokenInformation(tok, win32security.TokenUser)[0])
    return _SID


def _leer_i(ruta_i: str) -> tuple[str, float] | None:
    with open(ruta_i, 'rb') as f:
        datos = f.read()
    if len(datos) < 24:
        return None
    version, _tam, filetime = struct.unpack_from('<qqq', datos)
    if version == 2:
        n = struct.unpack_from('<i', datos, 24)[0]
        ruta = datos[28:28 + 2 * n].decode('utf-16-le')
    else:
        ruta = datos[24:24 + 520].decode('utf-16-le')
    fecha = (filetime - 116444736000000000) / 1e7
    return ruta.rstrip('\x00'), fecha


def buscar(original: str) -> list[tuple[float, str, str]]:
    """(fecha de borrado, ruta $R, ruta $I) de lo que estaba en «original», lo más reciente primero."""
    unidad = os.path.splitdrive(os.path.abspath(original))[0]
    papelera = os.path.join(unidad + os.sep, '$Recycle.Bin')
    objetivo = os.path.normcase(nfc(os.path.abspath(original)))
    res = []
    # En C: va por usuario ($Recycle.Bin\<SID>); en las unidades de Google Drive, en la raíz.
    for carpeta in (os.path.join(papelera, _sid()), papelera):
        try:
            nombres = os.listdir(carpeta)
        except OSError:
            continue
        for n in nombres:
            if not n.startswith('$I'):
                continue
            try:
                info = _leer_i(os.path.join(carpeta, n))
            except OSError:
                continue
            if info and os.path.normcase(nfc(info[0])) == objetivo:
                ruta_r = os.path.join(carpeta, '$R' + n[2:])
                if os.path.exists(ruta_r):
                    res.append((info[1], ruta_r, os.path.join(carpeta, n)))
    return sorted(res, reverse=True)


def restaurar(original: str, borrado_desde: float = 0) -> str:
    """Saca de la Papelera lo borrado de «original» (después de borrado_desde). Devuelve dónde quedó."""
    candidatos = [c for c in buscar(original) if c[0] >= borrado_desde - 60]
    if not candidatos:
        raise FileNotFoundError('ya no está en la Papelera (¿se vació?)')
    _fecha, ruta_r, ruta_i = candidatos[0]
    destino = original
    if os.path.exists(ruta_larga(destino)):
        base, ext = partir_ext(original)
        destino = f'{base} (recuperado {datetime.date.today():%Y-%m-%d}){ext}'
    os.makedirs(ruta_larga(os.path.dirname(destino)), exist_ok=True)
    shutil.move(ruta_r, ruta_larga(destino))
    try:
        os.remove(ruta_i)
    except OSError:
        pass
    return destino
