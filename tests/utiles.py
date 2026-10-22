"""Utilidades de las pruebas."""
from PIL import Image


def zona(ruta, referrer='', host=''):
    with open(ruta + ':Zone.Identifier', 'w') as f:
        f.write(f'[ZoneTransfer]\nZoneId=3\nReferrerUrl={referrer}\nHostUrl={host}\n')


def captura(ventana, archivo):
    """Foto de la ventana aunque otra la tape (PrintWindow)."""
    import ctypes
    import win32gui
    import win32ui
    hwnd = int(ventana.wm_frame(), 16)
    l, t, r, b = win32gui.GetWindowRect(hwnd)
    w, h = r - l, b - t
    hdc = win32gui.GetWindowDC(hwnd)
    dc = win32ui.CreateDCFromHandle(hdc)
    mem = dc.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(dc, w, h)
    mem.SelectObject(bmp)
    ctypes.windll.user32.PrintWindow(hwnd, mem.GetSafeHdc(), 2)
    im = Image.frombuffer('RGB', (w, h), bmp.GetBitmapBits(True), 'raw', 'BGRX', 0, 1)
    im.save(archivo)
    win32gui.DeleteObject(bmp.GetHandle())
    mem.DeleteDC()
    dc.DeleteDC()
    win32gui.ReleaseDC(hwnd, hdc)
    izq, arriba, der, abajo = __import__('organizador.sistema', fromlist=['x']).area_de_trabajo()
    return (l >= izq and t >= arriba and r <= der and b <= abajo), (l, t, r, b), (izq, arriba, der, abajo)
