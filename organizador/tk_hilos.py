"""Tk solo se toca desde el hilo de las ventanas, también al liberar memoria.

Python libera los objetos que ya nadie usa en el hilo que esté corriendo en ese momento. Si un hilo de
fondo libera una fuente, una variable o una imagen de Tk, tkinter llama a Tk desde ese hilo y se queda
esperando a que el hilo de las ventanas lo atienda; si el de las ventanas espera a su vez algo de ese
hilo (un candado), los dos se esperan para siempre. Así se colgó el programa nueve veces entre el 26 y
el 27-10-2026 (datos\\cuelgues.log): el índice liberaba fuentes de ventanas ya cerradas con su candado
cogido, y el icono pedía ese candado desde el hilo de las ventanas.

Aquí, esas liberaciones se apuntan y las hace el hilo de las ventanas en su siguiente vuelta (vaciar).
"""
import collections
import threading
import tkinter
import tkinter.font

_pendientes: collections.deque = collections.deque()
_hilo: int | None = None


def _aplazado(original):
    def __del__(self):
        if threading.get_ident() == _hilo:
            original(self)
        else:
            _pendientes.append((original, self))       # lo hace el hilo de las ventanas en vaciar()
    __del__.original = original
    return __del__


def instalar() -> None:
    """Desde el hilo de las ventanas, antes de abrir ninguna."""
    global _hilo
    if _hilo is None:
        clases = [tkinter.font.Font, tkinter.Variable, tkinter.Image]
        try:
            from PIL import ImageTk
            clases += [ImageTk.PhotoImage, ImageTk.BitmapImage]
        except ImportError:
            pass
        for c in clases:
            if not hasattr(c.__del__, 'original'):
                c.__del__ = _aplazado(c.__del__)
    _hilo = threading.get_ident()


def vaciar() -> None:
    """(hilo de las ventanas) Las liberaciones que dejaron apuntadas los demás hilos."""
    while _pendientes:
        original, obj = _pendientes.popleft()
        try:
            original(obj)
        except Exception:
            pass
        del obj
