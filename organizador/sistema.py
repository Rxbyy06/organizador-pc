"""Estado del PC con ctypes: inactividad, pantalla completa, batería, prioridad baja."""
import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
shell32 = ctypes.windll.shell32


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.UINT), ('dwTime', wintypes.DWORD)]


class _POWER(ctypes.Structure):
    _fields_ = [('ACLineStatus', ctypes.c_ubyte), ('BatteryFlag', ctypes.c_ubyte),
                ('BatteryLifePercent', ctypes.c_ubyte), ('SystemStatusFlag', ctypes.c_ubyte),
                ('BatteryLifeTime', wintypes.DWORD), ('BatteryFullLifeTime', wintypes.DWORD)]


def segundos_inactivo() -> float:
    info = _LASTINPUTINFO(ctypes.sizeof(_LASTINPUTINFO), 0)
    if not user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    return ((kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF) / 1000


class _MONITORINFO(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT), ('rcWork', wintypes.RECT),
                ('dwFlags', wintypes.DWORD)]


def pantalla_completa() -> bool:
    """Juego, película o presentación a pantalla completa."""
    estado = ctypes.c_int(0)
    # 2 = ocupado (app a pantalla completa), 3 = Direct3D, 4 = presentación
    if shell32.SHQueryUserNotificationState(ctypes.byref(estado)) == 0 and estado.value in (2, 3, 4):
        return True
    # Windows no siempre lo marca (p. ej. un vídeo a pantalla completa en el navegador): ¿la ventana activa
    # ocupa el monitor entero?
    user32.GetForegroundWindow.restype = wintypes.HWND
    hwnd = user32.GetForegroundWindow()
    if not hwnd or hwnd in (user32.GetDesktopWindow(), user32.GetShellWindow()):
        return False
    clase = ctypes.create_unicode_buffer(64)
    user32.GetClassNameW(hwnd, clase, 64)
    if clase.value in ('WorkerW', 'Progman', 'Shell_TrayWnd'):
        return False
    if user32.IsZoomed(hwnd):        # maximizada (con la barra de tareas oculta ocupa lo mismo): no es pantalla completa
        return False
    # La zona útil (sin barra de título): una ventana maximizada deja fuera título y barra de tareas.
    r = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(r)):
        return False
    esquina = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(esquina))
    r = wintypes.RECT(esquina.x, esquina.y, esquina.x + r.right, esquina.y + r.bottom)
    user32.MonitorFromWindow.restype = wintypes.HANDLE
    mon = user32.MonitorFromWindow(hwnd, 2)                         # MONITOR_DEFAULTTONEAREST
    info = _MONITORINFO()
    info.cbSize = ctypes.sizeof(info)
    if not user32.GetMonitorInfoW(wintypes.HANDLE(mon), ctypes.byref(info)):
        return False
    m = info.rcMonitor
    return r.left <= m.left and r.top <= m.top and r.right >= m.right and r.bottom >= m.bottom


def bateria_baja(umbral: int = 25) -> bool:
    p = _POWER()
    if not kernel32.GetSystemPowerStatus(ctypes.byref(p)):
        return False
    sin_cargador = p.ACLineStatus == 0
    return sin_cargador and p.BatteryLifePercent != 255 and p.BatteryLifePercent < umbral


def hilo_en_segundo_plano(activar: bool = True) -> None:
    """Baja a la vez la prioridad de procesador y de disco del hilo actual."""
    THREAD_MODE_BACKGROUND_BEGIN, THREAD_MODE_BACKGROUND_END = 0x00010000, 0x00020000
    kernel32.SetThreadPriority(kernel32.GetCurrentThread(),
                               THREAD_MODE_BACKGROUND_BEGIN if activar else THREAD_MODE_BACKGROUND_END)


def area_de_trabajo() -> tuple[int, int, int, int]:
    """Rectángulo de la pantalla sin la barra de tareas (izq, arriba, der, abajo)."""
    r = wintypes.RECT()
    user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0)   # SPI_GETWORKAREA
    return r.left, r.top, r.right, r.bottom


def rectangulo(hwnd: int) -> tuple[int, int, int, int] | None:
    r = wintypes.RECT()
    if not user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(r)):
        return None
    return r.left, r.top, r.right, r.bottom


class InstanciaUnica:
    """Mutex con nombre: impide abrir el programa dos veces."""

    def __init__(self, nombre: str):
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        self.handle = kernel32.CreateMutexW(None, False, nombre)
        self.ya_abierto = kernel32.GetLastError() == 183   # ERROR_ALREADY_EXISTS
