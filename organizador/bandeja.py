"""Icono junto al reloj (bandeja del sistema) con el menú de todo el programa.

El menú solo lee textos ya calculados: los cuenta un hilo propio («bandeja-estado») cuando se le pide
(actualizar, desde cualquier hilo) y cada minuto. Así ni el hilo del icono ni el de las ventanas esperan
nunca a un disco lento o a un candado de otro hilo.
"""
import logging
import threading

import pystray
from PIL import Image, ImageDraw

log = logging.getLogger(__name__)
AZUL, GRIS, NARANJA = (46, 125, 215, 255), (140, 140, 140, 255), (240, 140, 30, 255)


def imagen(pausado: bool = False, pendientes: int = 0) -> Image.Image:
    im = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    color = GRIS if pausado else AZUL
    d.rounded_rectangle((4, 10, 30, 22), 4, fill=color)               # pestaña
    d.rounded_rectangle((4, 16, 60, 56), 6, fill=color)                # carpeta
    d.polygon([(32, 48), (20, 34), (27, 34), (27, 22), (37, 22), (37, 34), (44, 34)], fill='white')  # flecha
    if pausado:
        d.rectangle((46, 2, 51, 16), fill=NARANJA)
        d.rectangle((55, 2, 60, 16), fill=NARANJA)
    elif pendientes:
        d.ellipse((42, 0, 63, 21), fill=NARANJA)
    return im


def _corta(texto: str, n: int) -> str:
    """Windows no admite textos más largos en el icono (y entonces no enseña nada)."""
    return texto if len(texto) <= n else texto[:n - 1] + '…'


class Bandeja:
    def __init__(self, app):
        self.app = app
        a = app
        self.estado = {'pendientes': 'Pendientes', 'revision': 'Revisión semanal', 'borrados': '',
                       'texto': 'Arrancando…', 'pausado': False}
        self._pedido = threading.Event()
        self._dibujo = None                          # (pausado, hay pendientes) del icono que se ve

        def e(clave):
            return lambda i: self.estado[clave]
        M = pystray.MenuItem
        menu = pystray.Menu(
            M(e('pendientes'), lambda: a.en_ui(a.abrir_pendientes), default=True),
            M('Historial…', lambda: a.en_ui(a.abrir_historial)),
            pystray.Menu.SEPARATOR,
            M(e('revision'), lambda: a.en_ui(a.abrir_revision)),
            M('Sincronizar ahora', lambda: a.sincronizar_ahora()),
            M(e('borrados'), lambda: a.en_ui(a.abrir_borrados), visible=lambda i: bool(self.estado['borrados'])),
            pystray.Menu.SEPARATOR,
            M(e('texto'), None, enabled=False),
            M('Pausar', pystray.Menu(
                M('1 hora', lambda: a.pausar(3600)),
                M('Hasta que lo reanude', lambda: a.pausar(None)),
            ), visible=lambda i: not self.estado['pausado']),
            M('Reanudar', lambda: a.reanudar(), visible=lambda i: self.estado['pausado']),
            pystray.Menu.SEPARATOR,
            M('Editar lo aprendido', lambda: a.abrir_archivo(a.cfg.aprendido)),
            M('Abrir configuración', lambda: a.abrir_archivo(a.cfg.archivo)),
            M('Salir', lambda: a.en_ui(a.salir)),
        )
        self.icono = pystray.Icon('OrganizadorPC', imagen(), 'Organizador del PC', menu)

    def arrancar(self):
        threading.Thread(target=self.icono.run, name='bandeja', daemon=True).start()
        threading.Thread(target=self._hilo_estado, name='bandeja-estado', daemon=True).start()

    def actualizar(self):
        """(desde cualquier hilo) Que se vuelvan a contar pendientes, avisos y estado. No espera a nada."""
        self._pedido.set()

    def _hilo_estado(self):
        while True:
            self._pedido.wait(60)                    # y cada minuto, por el «sincronizado hace N min»
            self._pedido.clear()
            try:
                self.refrescar()
            except Exception:
                log.exception('No pude actualizar el icono')

    def refrescar(self):
        a = self.app
        filas = a.pendientes()
        n = len(filas)
        avisos = sum(1 for _, _, quedan in filas if quedan <= a.cfg.dias_aviso * 86400)
        pausado = a.pausado()
        retenidos = len(a.sincro_retenidos)
        estado = {'pendientes': f'Pendientes ({n})', 'revision': f'Revisión semanal ({a.n_revision()})',
                  'borrados': f'Borrados por confirmar ({retenidos})' if retenidos else '',
                  'texto': a.texto_estado(), 'pausado': pausado}
        titulo = 'Organizador del PC' + (' · en pausa' if pausado else '') + \
            (f' · {n} pendiente{"s" if n != 1 else ""}' if n else '') + \
            (f' · {avisos} a la Papelera mañana' if avisos else '')
        if (pausado, bool(n)) != self._dibujo:
            self._dibujo = (pausado, bool(n))
            self.icono.icon = imagen(pausado, n)
        if _corta(titulo, 127) != self.icono.title:
            self.icono.title = _corta(titulo, 127)
        if estado != self.estado:
            self.estado = estado
            self.icono.update_menu()

    def notificar(self, titulo: str, texto: str):
        """Aviso de Windows (solo informa: no mueve nada)."""
        try:
            self.icono.notify(_corta(texto, 255), _corta(titulo, 63))
        except Exception:
            log.exception('No pude enseñar el aviso «%s»', titulo)

    def parar(self):
        self.icono.stop()
