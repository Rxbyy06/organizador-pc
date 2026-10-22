"""Ventanas: la de cada descarga, el selector de carpeta, Pendientes e Historial.

La revisión semanal de capturas está en ventanas_revision.py.
"""
import datetime
import os
import time
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from . import carpetas as C
from . import sistema
from .nombres import libre, nfc, ruta_valida, sanear

NARANJA = ('#B35C00', '#F0A040')
GRIS = ('#5F6368', '#A0A4A8')
ROJO = ('#C62828', '#FF6B6B')
VERDE = ('#2E7D32', '#7BC67E')
FUENTE = 13


def fuente(tam=FUENTE, negrita=False):
    return ctk.CTkFont(size=tam, weight='bold' if negrita else 'normal')


def ruta_bonita(cfg, ruta: str) -> str:
    rel = cfg.relativa(ruta)
    return 'OneDrive' if rel == '.' else rel.replace(os.sep, '  ›  ')


def _tamano(ventana) -> tuple[int, int]:
    """Tamaño exterior: contenido más barra de título y bordes."""
    ventana.update_idletasks()
    w = max(ventana.winfo_width(), ventana.winfo_reqwidth())
    h = max(ventana.winfo_height(), ventana.winfo_reqheight())
    exterior = sistema.rectangulo(int(ventana.wm_frame(), 16))
    dw, dh = (exterior[2] - exterior[0] - ventana.winfo_width(), exterior[3] - exterior[1] - ventana.winfo_height()) \
        if exterior else (0, 0)
    if not (0 <= dw <= 80 and 0 <= dh <= 120):          # aún sin dibujar: valores típicos de Windows 11
        dw, dh = 16, 48
    return w + dw, h + dh


def esquina(ventana, margen: int = 16) -> None:
    """Coloca la ventana abajo a la derecha, encima de la barra de tareas."""
    izq, arriba, der, abajo = sistema.area_de_trabajo()
    w, h = _tamano(ventana)
    ventana.geometry(f'+{max(izq, der - w - margen)}+{max(arriba, abajo - h - margen)}')


def centrar(ventana, sobre=None) -> None:
    w, h = _tamano(ventana)
    if sobre is not None and sobre.winfo_viewable():
        x = sobre.winfo_rootx() + (sobre.winfo_width() - w) // 2
        y = sobre.winfo_rooty() + (sobre.winfo_height() - h) // 2
    else:
        izq, arriba, der, abajo = sistema.area_de_trabajo()
        x, y = (izq + der - w) // 2, (arriba + abajo - h) // 2
    ventana.geometry(f'+{max(0, x)}+{max(0, y)}')


class Ventana(ctk.CTkToplevel):
    def __init__(self, master, titulo: str):
        super().__init__(master)
        self.withdraw()
        self.title(titulo)
        self.resizable(False, False)

    def mostrar(self, donde='esquina', sobre=None, encima=True):
        colocar = (lambda: esquina(self)) if donde == 'esquina' else (lambda: centrar(self, sobre))
        colocar()
        self.deiconify()
        if encima:
            self.attributes('-topmost', True)
        self.lift()
        self._colocar = colocar
        # customtkinter termina de ajustar tamaños (y el escalado de pantalla) un poco después.
        for ms in (60, 250):
            self.after(ms, lambda: (self.winfo_exists() and (colocar(), self.lift())))

    def recolocar(self):
        """Tras cambiar de tamaño (avisos que aparecen o desaparecen), que no se salga de la pantalla."""
        if getattr(self, '_colocar', None):
            self._colocar()


# ── Ventana de cada descarga ────────────────────────────────────────────────
class VentanaDescarga(Ventana):
    ANCHO = 600

    def __init__(self, app, s, numero: int, total: int):
        super().__init__(app.root, 'Nueva descarga')
        self.app, self.s, self.cfg = app, s, app.cfg
        self.carpeta = s.carpeta
        self.nombre_auto = s.nombre
        self.marcas: dict[tuple[str, str], tk.BooleanVar] = {}
        self.avisos = []
        self._pendiente = None
        self.descomprimir = tk.BooleanVar(value=s.es_zip and not s.zip.error)

        cuerpo = ctk.CTkFrame(self, fg_color='transparent')
        cuerpo.pack(fill='both', expand=True, padx=18, pady=(14, 12))
        cab = ctk.CTkFrame(cuerpo, fg_color='transparent')
        cab.pack(fill='x')
        ctk.CTkLabel(cab, text='Nueva descarga', font=fuente(16, True)).pack(side='left')
        if total > 1:
            ctk.CTkLabel(cab, text=f'{numero} de {total}', font=fuente(12), text_color=GRIS).pack(side='right')
        if self.cfg.simulacion:
            ctk.CTkLabel(cab, text='SIMULACIÓN', font=fuente(11, True), text_color=NARANJA).pack(side='right', padx=10)
        origen = s.origen.describir()
        info = f'{os.path.basename(s.archivo)}  ·  {_tam(s.tam)}' + (f'  ·  de {origen}' if origen else '')
        ctk.CTkLabel(cuerpo, text=info, font=fuente(12), text_color=GRIS, anchor='w', justify='left',
                     wraplength=self.ANCHO - 40).pack(fill='x', pady=(2, 10))

        ctk.CTkLabel(cuerpo, text='Carpeta', font=fuente(12, True), anchor='w').pack(fill='x')
        fila = ctk.CTkFrame(cuerpo, fg_color='transparent')
        fila.pack(fill='x')
        self.l_carpeta = ctk.CTkLabel(fila, text='', font=fuente(), anchor='w', justify='left',
                                      wraplength=self.ANCHO - 200)
        self.l_carpeta.pack(side='left', fill='x', expand=True)
        ctk.CTkButton(fila, text='Cambiar…', width=96, command=self.cambiar).pack(side='right')
        self.l_motivo = ctk.CTkLabel(cuerpo, text='', font=fuente(11), anchor='w', justify='left',
                                     wraplength=self.ANCHO - 40)
        self.l_motivo.pack(fill='x')
        self.l_crear = ctk.CTkLabel(cuerpo, text='', font=fuente(11), text_color=VERDE, anchor='w',
                                    justify='left', wraplength=self.ANCHO - 40)   # solo se ve si hace falta

        self.l_titulo_nombre = ctk.CTkLabel(cuerpo, text='Nombre', font=fuente(12, True), anchor='w')
        self.l_titulo_nombre.pack(fill='x', pady=(10, 0))
        fila = self.f_nombre = ctk.CTkFrame(cuerpo, fg_color='transparent')
        fila.pack(fill='x')
        self.e_nombre = ctk.CTkEntry(fila, font=fuente(), height=32)
        self.e_nombre.insert(0, s.nombre)
        self.e_nombre.pack(side='left', fill='x', expand=True)
        self.l_ext = ctk.CTkLabel(fila, text='', font=fuente(), text_color=GRIS)
        self.l_ext.pack(side='left', padx=(6, 0))
        self.e_nombre.bind('<KeyRelease>', lambda e: self._programar())
        self.l_error = ctk.CTkLabel(cuerpo, text='', font=fuente(11), text_color=ROJO, anchor='w')   # ídem

        if s.zip is not None:
            if s.zip.error:
                ctk.CTkLabel(cuerpo, text=f'ZIP: {s.zip.error}. Se moverá tal cual.', font=fuente(12),
                             text_color=NARANJA, anchor='w').pack(fill='x', pady=(4, 0))
            else:
                n = s.zip.total
                ctk.CTkCheckBox(cuerpo, text=f'Descomprimir aquí ({n} archivo{"s" if n != 1 else ""}, '
                                             f'{_tam(s.zip.tam)}) y mandar el zip a la Papelera',
                                variable=self.descomprimir, font=fuente(12),
                                command=self._cambio_zip).pack(fill='x', pady=(4, 0))
        self.f_avisos = ctk.CTkFrame(cuerpo, fg_color='transparent', height=1)
        self.f_avisos.pack(fill='x', pady=(6, 0))

        botones = ctk.CTkFrame(cuerpo, fg_color='transparent')
        botones.pack(fill='x', pady=(12, 0))
        self.b_aceptar = ctk.CTkButton(botones, text='Aceptar', width=120, font=fuente(13, True), command=self.aceptar)
        self.b_aceptar.pack(side='left')
        ctk.CTkButton(botones, text='Más tarde', width=110, fg_color='transparent', border_width=1,
                      text_color=('gray10', 'gray90'), command=self.mas_tarde).pack(side='left', padx=8)
        self.b_descartar = ctk.CTkButton(botones, text='Descartar', width=110, fg_color=ROJO,
                                         hover_color=('#9E1F1F', '#D45555'), command=self.descartar)
        self.protocol('WM_DELETE_WINDOW', self.mas_tarde)
        self.bind('<Return>', lambda e: self.aceptar())
        self.bind('<Escape>', lambda e: self.mas_tarde())
        self._refrescar()
        self.mostrar()

    # Estado
    @property
    def ext(self) -> str:
        return self.app.sugeridor.ext_final(self.s, self.descomprimir.get())

    def _carpeta_nueva(self) -> bool:
        return self.s.es_zip and self.descomprimir.get() and not self.s.zip.archivo_unico

    def _programar(self):
        if self._pendiente:
            self.after_cancel(self._pendiente)
        self._pendiente = self.after(300, self._refrescar)

    def _cambio_zip(self):
        if self.e_nombre.get().strip() == self.nombre_auto:
            self._poner_nombre(self.app.sugeridor.nombre_para(self.s, self.carpeta))
        self._refrescar()

    def _poner_nombre(self, nombre: str):
        self.nombre_auto = nombre
        self.e_nombre.delete(0, 'end')
        self.e_nombre.insert(0, nombre)

    def _refrescar(self):
        self._pendiente = None
        s = self.s
        self.l_carpeta.configure(text=ruta_bonita(self.cfg, self.carpeta))
        self.l_motivo.configure(text=('Por qué: ' + s.motivo) if self.carpeta == s.carpeta else 'Elegida por ti',
                                text_color=GRIS if (s.seguro or self.carpeta != s.carpeta) else NARANJA)
        faltan = [os.path.basename(c) for c in _faltan(self.carpeta)]
        if faltan:
            self.l_crear.configure(text='Se creará: ' + '  ›  '.join(faltan))
            self.l_crear.pack(fill='x', after=self.l_motivo)
        else:
            self.l_crear.pack_forget()
        self.l_titulo_nombre.configure(text='Carpeta nueva' if self._carpeta_nueva() else 'Nombre')
        self.l_ext.configure(text=self.ext or '(carpeta)')
        nombre = self.e_nombre.get().strip()
        error = ruta_valida(os.path.join(self.carpeta, nombre + self.ext)) if nombre else 'el nombre está vacío'
        if error:
            self.l_error.configure(text=f'No vale: {error}')
            self.l_error.pack(fill='x', after=self.f_nombre)
        else:
            self.l_error.pack_forget()
        self.b_aceptar.configure(state='disabled' if error else 'normal')

        self.avisos = self.app.sugeridor.avisos(s, self.carpeta, nombre, self.descomprimir.get()) if nombre else []
        for w in self.f_avisos.winfo_children():
            w.destroy()
        for a in self.avisos:
            color = NARANJA if a.tipo in ('casi', 'version') else ('gray10', 'gray90')
            ctk.CTkLabel(self.f_avisos, text='⚠ ' + a.texto, font=fuente(12), text_color=color, anchor='w',
                         justify='left', wraplength=self.ANCHO - 40).pack(fill='x', pady=(2, 0))
            if a.opcion:
                var = self.marcas.setdefault((a.tipo, a.ruta), tk.BooleanVar(value=a.marcado))
                ctk.CTkCheckBox(self.f_avisos, text=a.opcion, variable=var, font=fuente(12)).pack(
                    fill='x', padx=(18, 0), pady=(2, 2))
        if any(a.permite_descartar for a in self.avisos):
            self.b_descartar.pack(side='right')
        else:
            self.b_descartar.pack_forget()
        self.after(10, self.recolocar)

    # Botones
    def cambiar(self):
        SelectorCarpeta(self, self.app, self.carpeta, self._elegida)

    def _elegida(self, carpeta: str):
        editado = self.e_nombre.get().strip() != self.nombre_auto
        self.carpeta = carpeta
        if not editado:
            self._poner_nombre(self.app.sugeridor.nombre_para(self.s, carpeta))
        self._refrescar()

    def aceptar(self):
        if self.b_aceptar.cget('state') == 'disabled':
            return
        nombre = sanear(self.e_nombre.get().strip())
        quitar, docs_a_borrar = [], []
        for a in self.avisos:
            marcado = a.opcion and self.marcas[(a.tipo, a.ruta)].get()
            if a.tipo in ('version', 'enunciado_sobra') and marcado:
                quitar.append(a.ruta)
            elif a.tipo == 'version':
                nombre = libre(self.carpeta, nombre, self.ext)        # conservar las dos
            elif a.tipo == 'pdf_definitivo' and marcado:
                docs_a_borrar.append(a.ruta)
        destino = os.path.join(self.carpeta, nombre + self.ext)
        if not self._carpeta_nueva() and os.path.exists(destino) and destino not in quitar:
            nombre = libre(self.carpeta, nombre, self.ext)            # p. ej. guardar a propósito un idéntico
        self.destroy()
        self.app.aceptar(self.s, self.carpeta, nombre, self.descomprimir.get(), quitar, self.ext)
        for id_ in docs_a_borrar:
            self.app.borrar_doc(id_)

    def mas_tarde(self):
        self.destroy()
        self.app.mas_tarde(self.s)

    def descartar(self):
        self.destroy()
        self.app.descartar(self.s)


def _faltan(carpeta: str) -> list[str]:
    res = []
    while carpeta and not os.path.isdir(carpeta):
        res.append(carpeta)
        carpeta = os.path.dirname(carpeta)
    return list(reversed(res))


def _tam(n: int) -> str:
    for unidad in ('bytes', 'KB', 'MB', 'GB'):
        if n < 1024 or unidad == 'GB':
            return f'{n:.0f} {unidad}' if unidad in ('bytes', 'KB') else f'{n:.1f} {unidad}'.replace('.', ',')
        n /= 1024


# ── Selector de carpeta ─────────────────────────────────────────────────────
class SelectorCarpeta(Ventana):
    """Se abre en la carpeta sugerida, con sus hermanas. Las carpetas nuevas no se crean hasta «Aceptar»."""

    def __init__(self, padre, app, inicial: str, al_elegir):
        super().__init__(padre, 'Elegir carpeta')
        self.app, self.cfg, self.al_elegir = app, app.cfg, al_elegir
        self.raiz = os.path.normpath(self.cfg.onedrive)
        self.virtuales: set[str] = {os.path.normcase(c) for c in _faltan(inicial)}
        self.virtuales_ruta: dict[str, str] = {os.path.normcase(c): c for c in _faltan(inicial)}
        self.actual = os.path.dirname(inicial) if os.path.normpath(inicial) != self.raiz else self.raiz
        self.elegida = inicial
        self.ultimo_clic = (None, 0.0)

        cuerpo = ctk.CTkFrame(self, fg_color='transparent')
        cuerpo.pack(fill='both', expand=True, padx=16, pady=14)
        self.l_ruta = ctk.CTkLabel(cuerpo, text='', font=fuente(12, True), anchor='w', justify='left', wraplength=520)
        self.l_ruta.pack(fill='x')
        barra = ctk.CTkFrame(cuerpo, fg_color='transparent')
        barra.pack(fill='x', pady=(6, 6))
        self.b_subir = ctk.CTkButton(barra, text='↑ Subir', width=90, command=self.subir)
        self.b_subir.pack(side='left')
        ctk.CTkButton(barra, text='Nueva carpeta…', width=130, command=self.nueva).pack(side='left', padx=8)
        ctk.CTkLabel(barra, text='Doble clic para entrar', font=fuente(11), text_color=GRIS).pack(side='right')
        self.lista = ctk.CTkScrollableFrame(cuerpo, width=520, height=300)
        self.lista.pack(fill='both', expand=True)
        botones = ctk.CTkFrame(cuerpo, fg_color='transparent')
        botones.pack(fill='x', pady=(10, 0))
        self.b_elegir = ctk.CTkButton(botones, text='Elegir', width=200, command=self.elegir)
        self.b_elegir.pack(side='left')
        ctk.CTkButton(botones, text='Cancelar', width=100, fg_color='transparent', border_width=1,
                      text_color=('gray10', 'gray90'), command=self.destroy).pack(side='left', padx=8)
        self.bind('<Escape>', lambda e: self.destroy())
        self._pintar()
        self.mostrar('centro', padre)
        self.grab_set()

    def _hijas(self) -> list[tuple[str, bool]]:
        """(ruta, es_nueva) de las subcarpetas de la carpeta actual."""
        reales = [os.path.join(self.actual, d) for d in C.subcarpetas(self.actual)]
        vistas = {os.path.normcase(r) for r in reales}
        nuevas = [self.virtuales_ruta[v] for v in self.virtuales
                  if os.path.normcase(os.path.dirname(self.virtuales_ruta[v])) == os.path.normcase(self.actual)
                  and v not in vistas]
        # Dentro de una asignatura se ofrecen también las categorías que aún no existen.
        asig = C.asignatura_de(self.actual, self.cfg.ruta_uni)
        if asig and os.path.normcase(self.actual) == os.path.normcase(asig.base()):
            for cat in C.CATEGORIAS:
                r = asig.categoria(cat)
                if os.path.normcase(r) not in vistas and r not in nuevas:
                    nuevas.append(r)
        return sorted([(r, False) for r in reales] + [(r, True) for r in nuevas],
                      key=lambda x: nfc(os.path.basename(x[0])).casefold())

    def _pintar(self):
        self.l_ruta.configure(text=ruta_bonita(self.cfg, self.actual))
        self.b_subir.configure(state='disabled' if os.path.normcase(self.actual) == os.path.normcase(self.raiz)
                               else 'normal')
        for w in self.lista.winfo_children():
            w.destroy()
        for ruta, nueva in self._hijas():
            elegida = os.path.normcase(ruta) == os.path.normcase(self.elegida)
            texto = nfc(os.path.basename(ruta)) + ('   (nueva)' if nueva else '')
            b = ctk.CTkButton(self.lista, text='📁  ' + texto, anchor='w', height=30, font=fuente(),
                              fg_color=None if elegida else 'transparent',
                              text_color=('white', 'white') if elegida else (GRIS if nueva else ('gray10', 'gray90')),
                              hover_color=('gray80', 'gray30') if not elegida else None,
                              command=lambda r=ruta: self._clic(r))
            b.pack(fill='x', pady=1)
        if not self._hijas():
            ctk.CTkLabel(self.lista, text='(sin subcarpetas)', text_color=GRIS).pack(pady=10)
        self.b_elegir.configure(text=f'Elegir «{_corto(os.path.basename(self.elegida) or "OneDrive")}»')

    def _clic(self, ruta: str):
        ahora = time.time()
        if self.ultimo_clic[0] == ruta and ahora - self.ultimo_clic[1] < 0.45:
            self.actual = ruta                    # doble clic: entrar
        self.elegida = ruta
        self.ultimo_clic = (ruta, ahora)
        self._pintar()

    def subir(self):
        if os.path.normcase(self.actual) != os.path.normcase(self.raiz):
            self.elegida = self.actual
            self.actual = os.path.dirname(self.actual)
            self._pintar()

    def nueva(self):
        if os.path.normcase(self.actual) == os.path.normcase(self.cfg.ruta_uni):
            pista = 'Asignatura nueva, con el estilo «2n - T2 - Nom en català»:'
        else:
            pista = 'Nombre de la carpeta nueva:'
        d = ctk.CTkInputDialog(text=pista, title='Nueva carpeta')
        d.after(50, d.lift)
        nombre = d.get_input()
        if not nombre or not nombre.strip():
            return
        ruta = os.path.join(self.actual, sanear(nombre.strip()))
        if err := ruta_valida(ruta):
            messagebox.showerror('Nombre no válido', f'No vale: {err}', parent=self)
            return
        self.virtuales.add(os.path.normcase(ruta))
        self.virtuales_ruta[os.path.normcase(ruta)] = ruta
        self.elegida = self.actual = ruta
        self._pintar()

    def elegir(self):
        self.grab_release()
        self.destroy()
        self.al_elegir(self.elegida)


def _corto(t: str, n: int = 32) -> str:
    return t if len(t) <= n else t[:n - 1] + '…'


# ── Pendientes ──────────────────────────────────────────────────────────────
class VentanaPendientes(Ventana):
    def __init__(self, app):
        super().__init__(app.root, 'Pendientes de Descargas')
        self.app = app
        cuerpo = ctk.CTkFrame(self, fg_color='transparent')
        cuerpo.pack(fill='both', expand=True, padx=16, pady=14)
        ctk.CTkLabel(cuerpo, text='Pendientes en Descargas', font=fuente(16, True), anchor='w').pack(fill='x')
        ctk.CTkLabel(cuerpo, text=f'Lo que sigue en Descargas. «Organizar» abre la ventanita otra vez. A los '
                                  f'{app.cfg.dias_descargas:g} días de llegar, va a la Papelera (con un día de aviso).',
                     font=fuente(12), text_color=GRIS, anchor='w', justify='left', wraplength=600).pack(fill='x', pady=(0, 8))
        self.lista = ctk.CTkScrollableFrame(cuerpo, width=600, height=320)
        self.lista.pack(fill='both', expand=True)
        botones = ctk.CTkFrame(cuerpo, fg_color='transparent')
        botones.pack(fill='x', pady=(10, 0))
        ctk.CTkButton(botones, text='Abrir Descargas', width=140,
                      command=lambda: os.startfile(app.cfg.descargas)).pack(side='left')
        ctk.CTkButton(botones, text='Cerrar', width=100, fg_color='transparent', border_width=1,
                      text_color=('gray10', 'gray90'), command=self.destroy).pack(side='right')
        self.bind('<Escape>', lambda e: self.destroy())
        self.pintar()
        self.mostrar('centro', encima=False)

    def pintar(self):
        for w in self.lista.winfo_children():
            w.destroy()
        filas = self.app.pendientes()
        if not filas:
            ctk.CTkLabel(self.lista, text='Descargas está al día.', text_color=GRIS).pack(pady=20)
        aviso = self.app.cfg.dias_aviso * 86400
        for ruta, _desde, quedan in filas:
            f = ctk.CTkFrame(self.lista, fg_color='transparent')
            f.pack(fill='x', pady=2)
            dias = max(0, int(-(-quedan // 86400)))        # redondeo hacia arriba
            if quedan <= aviso:
                cuando, color = ('a la Papelera hoy' if dias == 0 else 'a la Papelera mañana'), NARANJA
            else:
                cuando, color = f'a la Papelera en {dias} días', GRIS
            carpeta = os.path.isdir(ruta)
            ctk.CTkLabel(f, text=('📁 ' if carpeta else '') + _corto(os.path.basename(ruta), 46), font=fuente(),
                         anchor='w').pack(side='left')
            if carpeta:
                ctk.CTkButton(f, text='Abrir', width=90, command=lambda r=ruta: os.startfile(r)).pack(side='right')
            else:
                ctk.CTkButton(f, text='Organizar', width=90, command=lambda r=ruta: self._organizar(r)).pack(side='right')
            ctk.CTkLabel(f, text=cuando, font=fuente(11), text_color=color).pack(side='right', padx=10)

    def _organizar(self, ruta):
        self.app.organizar(ruta)
        self.after(500, self.pintar)


# ── Historial ───────────────────────────────────────────────────────────────
class VentanaHistorial(Ventana):
    def __init__(self, app):
        super().__init__(app.root, 'Historial del Organizador')
        self.app = app
        cuerpo = ctk.CTkFrame(self, fg_color='transparent')
        cuerpo.pack(fill='both', expand=True, padx=16, pady=14)
        ctk.CTkLabel(cuerpo, text='Historial', font=fuente(16, True), anchor='w').pack(fill='x')
        ctk.CTkLabel(cuerpo, text=f'Lo que ha hecho el programa en los últimos {app.cfg.dias_historial} días. '
                                  '«Deshacer» lo devuelve como estaba (lo enviado a la Papelera se recupera de allí).',
                     font=fuente(12), text_color=GRIS, anchor='w', justify='left', wraplength=680).pack(fill='x', pady=(0, 8))
        self.lista = ctk.CTkScrollableFrame(cuerpo, width=680, height=380)
        self.lista.pack(fill='both', expand=True)
        ctk.CTkButton(cuerpo, text='Cerrar', width=100, fg_color='transparent', border_width=1,
                      text_color=('gray10', 'gray90'), command=self.destroy).pack(side='right', pady=(10, 0))
        self.bind('<Escape>', lambda e: self.destroy())
        self.pintar()
        self.mostrar('centro', encima=False)

    def pintar(self):
        for w in self.lista.winfo_children():
            w.destroy()
        filas = self.app.historial.lista()
        if not filas:
            ctk.CTkLabel(self.lista, text='Aún no hay nada.', text_color=GRIS).pack(pady=20)
        for id_, fecha, _tipo, descripcion, estado in filas:
            f = ctk.CTkFrame(self.lista, fg_color='transparent')
            f.pack(fill='x', pady=3)
            ctk.CTkLabel(f, text=datetime.datetime.fromtimestamp(fecha).strftime('%d/%m %H:%M'), width=80,
                         font=fuente(11), text_color=GRIS, anchor='nw').pack(side='left', anchor='n')
            if estado == 'hecho':
                ctk.CTkButton(f, text='Deshacer', width=86, command=lambda i=id_: self._deshacer(i)).pack(
                    side='right', anchor='n')
            else:
                etiqueta = {'deshecho': 'deshecho', 'simulado': 'simulación', 'error': 'falló',
                            'nota': 'en Drive'}.get(estado, estado)
                ctk.CTkLabel(f, text=etiqueta, width=86, font=fuente(11),
                             text_color=ROJO if estado == 'error' else GRIS).pack(side='right', anchor='n')
            ctk.CTkLabel(f, text=descripcion, font=fuente(12), anchor='w', justify='left',
                         wraplength=480, text_color=GRIS if estado == 'deshecho' else ('gray10', 'gray90')).pack(
                side='left', fill='x', expand=True, padx=6)

    def _deshacer(self, id_):
        self.app.deshacer(id_, al_terminar=self.pintar)
