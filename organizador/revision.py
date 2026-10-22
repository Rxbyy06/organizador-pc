"""Revisión semanal de capturas y grabaciones de pantalla."""
import ctypes
import datetime
import os
import re
import time
from ctypes import wintypes

from PIL import Image

from .huellas import ignorado

DIA = 86400
IMAGENES = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.heic'}
VIDEOS = {'.mp4', '.mkv', '.mov', '.avi', '.webm', '.wmv'}


class Revision:
    def __init__(self, cfg, historial, ahora=time.time):
        self.cfg, self.historial, self.ahora = cfg, historial, ahora

    def pendientes(self) -> list[str]:
        """Capturas de más de N días, de la más antigua a la más nueva.

        Las marcadas «Dejar» siguen saliendo cada semana; pasado el plazo (4 semanas) desde la
        primera vez, se quedan para siempre y ya no salen.
        """
        ahora, res = self.ahora(), []
        for carpeta in self.cfg.carpetas_capturas:
            try:
                entradas = list(os.scandir(carpeta))
            except OSError:
                continue
            for e in entradas:
                ext = os.path.splitext(e.name)[1].lower()
                if not e.is_file() or ignorado(e.name) or ext not in IMAGENES | VIDEOS:
                    continue
                fecha = fecha_de(e.path)
                if ahora - fecha >= self.cfg.dias_capturas * DIA and not self.conservada(e.path):
                    res.append((fecha, e.path))
        return [r for _, r in sorted(res)]

    def conservada(self, ruta: str) -> bool:
        """Dejada hace más del plazo: ya es para quedársela."""
        desde = self.historial.dejada_desde(ruta)
        return desde is not None and self.ahora() - desde >= self.cfg.semanas_dejar * 7 * DIA

    def dejada(self, ruta: str) -> float | None:
        return self.historial.dejada_desde(ruta)

    def ultimo_turno(self) -> float:
        """El último día de revisión (a las 00:00) que ya ha llegado."""
        hoy = datetime.datetime.fromtimestamp(self.ahora()).replace(hour=0, minute=0, second=0, microsecond=0)
        dias_atras = (hoy.weekday() - self.cfg.dia_revision) % 7
        return (hoy - datetime.timedelta(days=dias_atras)).timestamp()

    def turno_pendiente(self) -> bool:
        """¿Ha llegado el día de la revisión semanal (o pasó con el PC apagado) y aún no se ha hecho?"""
        return (self.historial.leer_estado('ultima_revision') < self.ultimo_turno()
                and self.historial.leer_estado('revision_pospuesta') <= self.ahora())

    def toca(self) -> bool:
        """¿Hay que abrir la revisión sola? (el día que toca o, si el PC estaba apagado, el primer arranque después)."""
        if self.historial.leer_estado('ultima_revision') >= self.ultimo_turno():
            return False
        if self.historial.leer_estado('revision_pospuesta') > self.ahora():
            return False
        if not self.pendientes():
            self.hecha()                       # nada que revisar esta semana
            return False
        return True

    def hecha(self) -> None:
        self.historial.poner_estado('ultima_revision', self.ahora())

    def posponer(self) -> None:
        """«Más tarde»: vuelve a salir mañana."""
        self.historial.poner_estado('revision_pospuesta', self.ahora() + DIA - 3600)

    def dejar(self, ruta: str) -> None:
        self.historial.dejar(ruta, self.ahora())


def fecha_de(ruta: str) -> float:
    """Cuándo se hizo la captura: la fecha del nombre («Captura de pantalla 2026-10-21 121613») o la del archivo."""
    if m := re.search(r'(20\d\d)-(\d\d)-(\d\d)[ _](\d\d)(\d\d)(\d\d)', os.path.basename(ruta)):
        try:
            return datetime.datetime(*map(int, m.groups())).timestamp()
        except ValueError:
            pass
    st = os.stat(ruta)
    return min(st.st_mtime, st.st_ctime)


def nombre_sugerido(ruta: str) -> str:
    """«Captura 2026-10-21» (o «Grabación …» si es vídeo), con la extensión original."""
    ext = os.path.splitext(ruta)[1].lower()
    tipo = 'Grabación' if ext in VIDEOS else 'Captura'
    return f'{tipo} {datetime.datetime.fromtimestamp(fecha_de(ruta)):%Y-%m-%d}{ext}'


# ── Miniaturas: las mismas que enseña el Explorador (también para vídeos) ──
class _SIZE(ctypes.Structure):
    _fields_ = [('cx', wintypes.LONG), ('cy', wintypes.LONG)]


class _BITMAP(ctypes.Structure):
    _fields_ = [('bmType', wintypes.LONG), ('bmWidth', wintypes.LONG), ('bmHeight', wintypes.LONG),
                ('bmWidthBytes', wintypes.LONG), ('bmPlanes', wintypes.WORD), ('bmBitsPixel', wintypes.WORD),
                ('bmBits', ctypes.c_void_p)]


class _GUID(ctypes.Structure):
    _fields_ = [('a', wintypes.DWORD), ('b', wintypes.WORD), ('c', wintypes.WORD), ('d', ctypes.c_ubyte * 8)]


_IID_FACTORY = _GUID(0xBCC18B79, 0xBA16, 0x442F, (ctypes.c_ubyte * 8)(0x80, 0xC4, 0x8A, 0x59, 0xC3, 0x0C, 0x46, 0x3B))


def _miniatura_windows(ruta: str, lado: int) -> Image.Image | None:
    ctypes.windll.ole32.CoInitialize(None)
    fabrica = ctypes.c_void_p()
    shell32 = ctypes.windll.shell32
    shell32.SHCreateItemFromParsingName.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(_GUID),
                                                    ctypes.POINTER(ctypes.c_void_p)]
    if shell32.SHCreateItemFromParsingName(os.path.normpath(ruta), None, ctypes.byref(_IID_FACTORY),
                                           ctypes.byref(fabrica)) != 0:
        return None
    vtabla = ctypes.cast(ctypes.cast(fabrica, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
    get_image = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, _SIZE, ctypes.c_int,
                                   ctypes.POINTER(wintypes.HBITMAP))(vtabla[3])
    release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtabla[2])
    hbmp = wintypes.HBITMAP()
    try:
        if get_image(fabrica, _SIZE(lado, lado), 0, ctypes.byref(hbmp)) != 0:   # SIIGBF_RESIZETOFIT
            return None
        gdi32 = ctypes.windll.gdi32
        bm = _BITMAP()
        gdi32.GetObjectW(hbmp, ctypes.sizeof(bm), ctypes.byref(bm))
        datos = ctypes.create_string_buffer(bm.bmWidthBytes * bm.bmHeight)
        gdi32.GetBitmapBits(hbmp, len(datos), datos)
        im = Image.frombuffer('RGBA', (bm.bmWidth, bm.bmHeight), datos.raw, 'raw', 'BGRA', bm.bmWidthBytes, 1)
        gdi32.DeleteObject(hbmp)
        return im.convert('RGB')
    finally:
        release(fabrica)


def miniatura(ruta: str, lado: int = 220) -> Image.Image:
    try:
        if im := _miniatura_windows(ruta, lado):
            return im
    except Exception:
        pass
    if os.path.splitext(ruta)[1].lower() in IMAGENES:
        try:
            im = Image.open(ruta)
            im.thumbnail((lado, lado))
            return im.convert('RGB')
        except Exception:
            pass
    im = Image.new('RGB', (lado, int(lado * 0.6)), (90, 90, 90))      # sin miniatura: un recuadro gris
    return im
