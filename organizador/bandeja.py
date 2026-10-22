"""Icono junto al reloj (bandeja del sistema) con el menú de todo el programa."""
import pystray
from PIL import Image, ImageDraw

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


class Bandeja:
    def __init__(self, app):
        self.app = app
        a = app
        M = pystray.MenuItem
        menu = pystray.Menu(
            M(lambda i: f'Pendientes ({a.n_pendientes()})', lambda: a.en_ui(a.abrir_pendientes), default=True),
            M('Historial…', lambda: a.en_ui(a.abrir_historial)),
            pystray.Menu.SEPARATOR,
            M(lambda i: f'Revisión semanal ({a.n_revision()})', lambda: a.en_ui(a.abrir_revision)),
            M('Sincronizar ahora', lambda: a.sincronizar_ahora()),
            M(lambda i: f'Borrados por confirmar ({len(a.sincro_retenidos)})', lambda: a.en_ui(a.abrir_borrados),
              visible=lambda i: bool(a.sincro_retenidos)),
            pystray.Menu.SEPARATOR,
            M(lambda i: a.texto_estado(), None, enabled=False),
            M('Pausar', pystray.Menu(
                M('1 hora', lambda: a.pausar(3600)),
                M('Hasta que lo reanude', lambda: a.pausar(None)),
            ), visible=lambda i: not a.pausado()),
            M('Reanudar', lambda: a.reanudar(), visible=lambda i: a.pausado()),
            pystray.Menu.SEPARATOR,
            M('Editar lo aprendido', lambda: a.abrir_archivo(a.cfg.aprendido)),
            M('Abrir configuración', lambda: a.abrir_archivo(a.cfg.archivo)),
            M('Salir', lambda: a.en_ui(a.salir)),
        )
        self.icono = pystray.Icon('OrganizadorPC', imagen(), 'Organizador del PC', menu)

    def arrancar(self):
        import threading
        threading.Thread(target=self.icono.run, name='bandeja', daemon=True).start()

    def actualizar(self):
        n, avisos = self.app.n_pendientes(), self.app.n_avisos()
        self.icono.icon = imagen(self.app.pausado(), n)
        self.icono.title = 'Organizador del PC' + (' · en pausa' if self.app.pausado() else '') + \
            (f' · {n} pendiente{"s" if n != 1 else ""}' if n else '') + \
            (f' · {avisos} a la Papelera mañana' if avisos else '')
        self.icono.update_menu()

    def notificar(self, titulo: str, texto: str):
        """Aviso de Windows (solo informa: no mueve nada)."""
        try:
            self.icono.notify(texto, titulo)
        except Exception:
            pass

    def parar(self):
        self.icono.stop()
