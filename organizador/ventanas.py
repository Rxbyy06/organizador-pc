"""Ventanas: la de cada descarga, Pendientes, Historial y las listas de rutas que usan todas.

La revisión semanal está en ventanas_revision.py; las del sincronizador, en ventanas_sincro.py.
"""
import datetime
import os
import subprocess
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, ttk

import customtkinter as ctk

from . import sistema
from .nombres import libre, ruta_valida, sanear

NARANJA = ('#B35C00', '#F0A040')
GRIS = ('#5F6368', '#A0A4A8')
ROJO = ('#C62828', '#FF6B6B')
VERDE = ('#2E7D32', '#7BC67E')
FUENTE = 13
_fuentes: dict = {}


def fuente(tam=FUENTE, negrita=False):
    """Una sola por tamaño y grosor para todo el programa: crear una en cada etiqueta dejaba muchas por
    liberar al cerrar cada ventana (y liberarlas desde otro hilo colgaba el programa: ver tk_hilos)."""
    k = (tk._default_root, tam, negrita)
    if k not in _fuentes:
        _fuentes[k] = ctk.CTkFont(size=tam, weight='bold' if negrita else 'normal')
    return _fuentes[k]


def ruta_bonita(cfg, ruta: str) -> str:
    rel = cfg.relativa(ruta)
    return 'OneDrive' if rel == '.' else rel.replace(os.sep, '  ›  ')


def carpeta_corta(cfg, ruta: str) -> str:
    """La carpeta de un archivo para una lista: relativa a OneDrive (o entera si está fuera)."""
    rel = cfg.relativa(os.path.dirname(ruta))
    return 'OneDrive' if rel == '.' else rel


def mostrar_en_explorador(ruta: str) -> None:
    """Abre su carpeta en el Explorador con el archivo marcado (o la carpeta más cercana que exista)."""
    ruta = os.path.normpath(ruta)
    if os.path.exists(ruta):
        subprocess.Popen(f'explorer /select,"{ruta}"')
        return
    while ruta and not os.path.isdir(ruta) and os.path.dirname(ruta) != ruta:
        ruta = os.path.dirname(ruta)
    if os.path.isdir(ruta):
        os.startfile(ruta)


def existente(carpeta: str) -> str:
    """La carpeta, o la más cercana hacia arriba que ya exista."""
    while carpeta and not os.path.isdir(carpeta) and os.path.dirname(carpeta) != carpeta:
        carpeta = os.path.dirname(carpeta)
    return carpeta


def elegir_carpeta(padre, inicial: str, titulo: str) -> str | None:
    """El selector de carpetas de Windows (el del Explorador), abierto en «inicial» o en lo más cercano que
    exista. None si se cancela."""
    elegida = filedialog.askdirectory(parent=padre, initialdir=existente(inicial) or None, title=titulo,
                                      mustexist=False)
    return os.path.normpath(elegida) if elegida else None


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
    def __init__(self, master, titulo: str, redimensionable: bool = False):
        super().__init__(master)
        self.withdraw()
        self.title(titulo)
        # Una sola vez: cada resizable() hace que customtkinter oculte y vuelva a enseñar la ventana un momento
        # (para pintar la barra de título), y dos seguidos la dejan oculta para siempre.
        self.resizable(redimensionable, redimensionable)

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


# ── Listas de rutas ─────────────────────────────────────────────────────────
_estilos: dict = {}


def _estilo_tablas(w) -> tuple[tkfont.Font, tkfont.Font, int]:
    """Las listas son de ttk: con los colores y la letra de customtkinter (claro u oscuro, y a escala)."""
    oscuro = ctk.get_appearance_mode() == 'Dark'
    escala = ctk.ScalingTracker.get_widget_scaling(w)
    k = (tk._default_root, oscuro, escala)
    if k in _estilos:
        return _estilos[k]
    tema = ctk.ThemeManager.theme

    def color(par):
        return par[1] if oscuro else par[0]
    familia = tema['CTkFont']['family']
    letra = tkfont.Font(family=familia, size=-round(13 * escala))
    negrita = tkfont.Font(family=familia, size=-round(13 * escala), weight='bold')
    alto_fila = letra.metrics('linespace') + round(8 * escala)
    fondo, texto = color(tema['CTkTextbox']['fg_color']), color(tema['CTkLabel']['text_color'])
    s = ttk.Style(w)
    if s.theme_use() != 'clam':
        s.theme_use('clam')                     # el de Windows no deja cambiar los colores
    s.configure('Rutas.Treeview', background=fondo, fieldbackground=fondo, foreground=texto, font=letra,
                rowheight=alto_fila, borderwidth=0, relief='flat')
    s.map('Rutas.Treeview', background=[('selected', color(tema['CTkButton']['fg_color']))],
          foreground=[('selected', 'white')])
    s.configure('Rutas.Treeview.Heading', background=color(tema['CTkFrame']['top_fg_color']), foreground=texto,
                font=negrita, relief='flat', borderwidth=0, padding=(4, 3))
    s.map('Rutas.Treeview.Heading', background=[('active', color(tema['CTkFrame']['fg_color']))])
    s.layout('Rutas.Treeview', [('Treeview.treearea', {'sticky': 'nswe'})])      # sin marco
    _estilos[k] = (letra, negrita, alto_fila)
    return _estilos[k]


class TablaRutas(ctk.CTkFrame):
    """Lista de archivos con su ruta entera, como en el Explorador: el nombre primero (lo que distingue un
    archivo de otro siempre se ve) y barras para desplazarse en horizontal y en vertical (Mayús + rueda,
    en horizontal). Con «arbol», unas filas cuelgan de otras (los archivos de su carpeta).

    columnas: [(título, ancho mínimo)]. Doble clic o Intro: al_abrir(valor de la fila).
    La tabla tiene su propio tamaño (el de las columnas al mínimo y «alto» filas; más si se agranda la
    ventana): unas columnas anchas no ensanchan la ventana, sacan la barra horizontal."""

    def __init__(self, padre, columnas: list[tuple[str, int]], alto: int = 10, al_abrir=None,
                 arbol: bool = False, varias: bool = False):
        escala = ctk.ScalingTracker.get_widget_scaling(padre)
        self.letra, self.negrita, alto_fila = _estilo_tablas(padre)
        filas_px = alto * alto_fila + self.negrita.metrics('linespace') + round(12 * escala)
        super().__init__(padre, fg_color='transparent', width=sum(m for _, m in columnas) + 20,
                         height=round(filas_px / escala) + 20)
        self.grid_propagate(False)
        self.arbol, self.al_abrir, self.alto = arbol, al_abrir, alto
        self.minimos = [round(m * escala) for _, m in columnas]
        self.valores: dict[str, object] = {}
        ids = [f'c{i}' for i in range(len(columnas))]
        self.cols = ['#0'] + ids[1:] if arbol else ids
        self.t = ttk.Treeview(self, columns=ids[1:] if arbol else ids, show='tree headings' if arbol else 'headings',
                              height=alto, style='Rutas.Treeview', selectmode='extended' if varias else 'browse')
        for c, (titulo, _), minimo in zip(self.cols, columnas, self.minimos):
            self.t.heading(c, text=titulo, anchor='w')
            self.t.column(c, width=minimo, minwidth=minimo, stretch=False, anchor='w')
        xs = ctk.CTkScrollbar(self, orientation='horizontal', command=self.t.xview, height=16)
        ys = ctk.CTkScrollbar(self, orientation='vertical', command=self.t.yview, width=16)

        def vertical(a, b):                     # la vertical, solo si hay más filas de las que caben
            ys.set(a, b)
            if float(a) <= 0 and float(b) >= 1:
                ys.grid_remove()
            else:
                ys.grid()
        self.t.configure(xscrollcommand=xs.set, yscrollcommand=vertical)
        self.t.grid(row=0, column=0, sticky='nsew')
        ys.grid(row=0, column=1, sticky='ns')
        xs.grid(row=1, column=0, sticky='ew')
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        modo = 1 if ctk.get_appearance_mode() == 'Dark' else 0
        self.t.tag_configure('aviso', foreground=NARANJA[modo])
        self.t.tag_configure('gris', foreground=GRIS[modo])
        self.t.tag_configure('carpeta', font=self.negrita)
        self.t.bind('<Double-1>', self._doble)
        self.t.bind('<Return>', lambda e: self._abrir(self.t.focus()))
        self.t.bind('<Shift-MouseWheel>', lambda e: self.t.xview_scroll(-3 if e.delta > 0 else 3, 'units'))

    def anadir(self, textos: list[str], valor=None, padre: str = '', abierta: bool = False,
               etiqueta: str | None = None) -> str:
        """Una fila; «valor» es lo que reciben al_abrir y elegidos()."""
        if self.arbol:
            iid = self.t.insert(padre, 'end', text=textos[0], values=textos[1:], open=abierta,
                                tags=(etiqueta,) if etiqueta else ())
        else:
            iid = self.t.insert('', 'end', values=textos, tags=(etiqueta,) if etiqueta else ())
        self.valores[iid] = valor
        return iid

    def vaciar(self) -> None:
        self.t.delete(*self.t.get_children())
        self.valores.clear()

    def quitar(self, iid: str) -> None:
        if self.t.exists(iid):
            self.t.delete(iid)
        self.valores.pop(iid, None)

    def ajustar(self) -> None:
        """Cada columna, tan ancha como su texto más largo: lo que no cabe se ve con la barra horizontal."""
        anchos = list(self.minimos)
        pila = [(i, 0) for i in self.t.get_children()]
        while pila:
            iid, nivel = pila.pop()
            item = self.t.item(iid)
            letra = self.negrita if 'carpeta' in item['tags'] else self.letra
            textos = ([item['text']] if self.arbol else []) + [str(v) for v in item['values']]
            for n, texto in enumerate(textos):
                extra = 30 + 20 * nivel if self.arbol and n == 0 else 16
                anchos[n] = max(anchos[n], letra.measure(texto) + extra)
            pila += [(h, nivel + 1) for h in self.t.get_children(iid)]
        for c, ancho in zip(self.cols, anchos):
            self.t.column(c, width=ancho, minwidth=ancho)

    def elegidos(self) -> list:
        return [self.valores[i] for i in self.t.selection() if self.valores.get(i) is not None]

    def elegidas(self) -> list[str]:
        """Las filas marcadas (sus identificadores)."""
        return [i for i in self.t.selection() if self.valores.get(i) is not None]

    def _doble(self, e):
        iid = self.t.identify_row(e.y)
        if iid and self.t.identify_region(e.x, e.y) != 'heading':
            self._abrir(iid)

    def _abrir(self, iid):
        if iid and self.al_abrir and self.valores.get(iid) is not None:
            self.al_abrir(self.valores[iid])


# ── Ventana de cada descarga ────────────────────────────────────────────────
class VentanaDescarga(Ventana):
    ANCHO = 600

    def __init__(self, app, s, numero: int, total: int):
        super().__init__(app.root, 'Nueva descarga')
        self.app, self.s, self.cfg = app, s, app.cfg
        self.carpeta = s.carpeta
        self.cambiada = False                       # la ha elegido él con «Cambiar…»
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

    def _sin_carpeta(self) -> bool:
        """No sé dónde va (la raíz de OneDrive o de la uni) y aún no la ha elegido: antes de nada, que elija."""
        raices = {os.path.normcase(os.path.normpath(r)) for r in (self.cfg.onedrive, self.cfg.ruta_uni)}
        return not self.cambiada and os.path.normcase(os.path.normpath(self.carpeta)) in raices

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
        descargas = os.path.normcase(os.path.normpath(self.cfg.descargas))
        if os.path.normcase(self.carpeta) == descargas or os.path.normcase(self.carpeta).startswith(descargas + os.sep):
            error = 'elige una carpeta fuera de Descargas'
        if error:
            self.l_error.configure(text=f'No vale: {error}')
            self.l_error.pack(fill='x', after=self.f_nombre)
        else:
            self.l_error.pack_forget()
        self.b_aceptar.configure(state='disabled' if error else 'normal',
                                 text='Elegir carpeta…' if self._sin_carpeta() else 'Aceptar')

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
        carpeta = elegir_carpeta(self, self.carpeta, f'¿Dónde guardo «{os.path.basename(self.s.archivo)}»?')
        if not self.winfo_exists():                 # se cerró mientras (p. ej., lo moviste tú a mano)
            return
        if carpeta:
            self._elegida(carpeta)
        self.lift()
        self.e_nombre.focus_set()

    def _elegida(self, carpeta: str):
        editado = self.e_nombre.get().strip() != self.nombre_auto
        self.carpeta = carpeta
        self.cambiada = True
        if not editado:
            self._poner_nombre(self.app.sugeridor.nombre_para(self.s, carpeta))
        self._refrescar()

    def aceptar(self):
        if self.b_aceptar.cget('state') == 'disabled':
            return
        if self._sin_carpeta():
            self.cambiar()
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
            if not self.s.es_zip and self.app.sugeridor.es_igual(destino, self.s):
                # Ya está ahí, idéntico: guardarlo otra vez solo crearía «… (2)». Lo que sobra es la descarga.
                self.destroy()
                self.app.descartar(self.s, ya_estaba=destino)
                return
            nombre = libre(self.carpeta, nombre, self.ext)            # mismo nombre, otro contenido: las dos
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


def _corto(t: str, n: int = 32) -> str:
    return t if len(t) <= n else t[:n - 1] + '…'


def _boton_secundario(padre, texto, orden, ancho=100):
    return ctk.CTkButton(padre, text=texto, width=ancho, fg_color='transparent', border_width=1,
                         text_color=('gray10', 'gray90'), command=orden)


# ── Pendientes ──────────────────────────────────────────────────────────────
class VentanaPendientes(Ventana):
    def __init__(self, app):
        super().__init__(app.root, 'Pendientes de Descargas', redimensionable=True)
        self.app = app
        cuerpo = ctk.CTkFrame(self, fg_color='transparent')
        cuerpo.pack(fill='both', expand=True, padx=16, pady=14)
        ctk.CTkLabel(cuerpo, text='Pendientes en Descargas', font=fuente(16, True), anchor='w').pack(fill='x')
        ctk.CTkLabel(cuerpo, text=f'Lo que sigue en Descargas. «Organizar» (o doble clic) abre la ventanita otra vez. '
                                  f'A los {app.cfg.dias_descargas:g} días de llegar, va a la Papelera (con un día de aviso).',
                     font=fuente(12), text_color=GRIS, anchor='w', justify='left', wraplength=640).pack(fill='x', pady=(0, 8))
        self.tabla = TablaRutas(cuerpo, [('A la Papelera', 130), ('Llegó', 70), ('Archivo', 420)], alto=12,
                                al_abrir=self._abrir, varias=True)
        self.tabla.pack(fill='both', expand=True)
        self.l_vacio = ctk.CTkLabel(cuerpo, text='Descargas está al día.', text_color=GRIS)
        botones = ctk.CTkFrame(cuerpo, fg_color='transparent')
        botones.pack(fill='x', pady=(10, 0))
        ctk.CTkButton(botones, text='Organizar', width=110, command=self._organizar).pack(side='left')
        _boton_secundario(botones, 'Abrir', self._abrir_elegidos, 90).pack(side='left', padx=8)
        _boton_secundario(botones, 'Abrir Descargas', lambda: os.startfile(app.cfg.descargas), 140).pack(side='left')
        _boton_secundario(botones, 'Cerrar', self.destroy).pack(side='right')
        self.bind('<Escape>', lambda e: self.destroy())
        self.pintar()
        self.mostrar('centro', encima=False)

    def pintar(self):
        antes = set(self.tabla.elegidos())
        self.tabla.vaciar()
        aviso = self.app.cfg.dias_aviso * 86400
        filas = self.app.pendientes()
        for ruta, desde, quedan in filas:
            dias = max(0, int(-(-quedan // 86400)))        # redondeo hacia arriba
            if quedan <= aviso:
                cuando = 'hoy' if dias == 0 else 'mañana'
            else:
                cuando = f'en {dias} días'
            nombre = os.path.basename(ruta) + ('  (carpeta)' if os.path.isdir(ruta) else '')
            iid = self.tabla.anadir([cuando, f'{datetime.datetime.fromtimestamp(desde):%d/%m}', nombre], ruta,
                                    etiqueta='aviso' if quedan <= aviso else None)
            if ruta in antes:
                self.tabla.t.selection_add(iid)
        self.tabla.ajustar()
        if filas:
            self.l_vacio.pack_forget()
        else:
            self.l_vacio.pack(pady=(8, 0), before=self.tabla)

    def _abrir(self, ruta):
        """Doble clic: un archivo se organiza; una carpeta se abre."""
        if os.path.isdir(ruta):
            os.startfile(ruta)
        else:
            self._organizar([ruta])

    def _abrir_elegidos(self):
        for ruta in self.tabla.elegidos():
            if os.path.exists(ruta):
                os.startfile(ruta)

    def _organizar(self, rutas=None):
        for ruta in reversed(rutas or self.tabla.elegidos()):      # (se ponen delante de la cola)
            if os.path.isfile(ruta):
                self.app.organizar(ruta)
        self.after(500, self.pintar)


# ── Historial ───────────────────────────────────────────────────────────────
class VentanaHistorial(Ventana):
    ESTADOS = {'hecho': 'hecho', 'deshecho': 'deshecho', 'simulado': 'simulación', 'error': 'falló', 'nota': 'en Drive'}

    def __init__(self, app):
        super().__init__(app.root, 'Historial del Organizador', redimensionable=True)
        self.app = app
        cuerpo = ctk.CTkFrame(self, fg_color='transparent')
        cuerpo.pack(fill='both', expand=True, padx=16, pady=14)
        ctk.CTkLabel(cuerpo, text='Historial', font=fuente(16, True), anchor='w').pack(fill='x')
        ctk.CTkLabel(cuerpo, text=f'Lo que ha hecho el programa en los últimos {app.cfg.dias_historial} días. Marca una '
                                  'fila: «Deshacer» la devuelve como estaba (lo enviado a la Papelera se recupera de allí) '
                                  'y «Ver archivos» (o doble clic) enseña cada archivo con su ruta entera.',
                     font=fuente(12), text_color=GRIS, anchor='w', justify='left', wraplength=760).pack(fill='x', pady=(0, 8))
        self.tabla = TablaRutas(cuerpo, [('Cuándo', 96), ('Estado', 90), ('Qué ha hecho', 560)], alto=16,
                                al_abrir=self._ver)
        self.tabla.pack(fill='both', expand=True)
        botones = ctk.CTkFrame(cuerpo, fg_color='transparent')
        botones.pack(fill='x', pady=(10, 0))
        self.b_deshacer = ctk.CTkButton(botones, text='Deshacer', width=110, command=self._deshacer)
        self.b_deshacer.pack(side='left')
        self.b_ver = _boton_secundario(botones, 'Ver archivos', lambda: self._ver(), 120)
        self.b_ver.pack(side='left', padx=8)
        _boton_secundario(botones, 'Cerrar', self.destroy).pack(side='right')
        self.tabla.t.bind('<<TreeviewSelect>>', lambda e: self._botones())
        self.bind('<Escape>', lambda e: self.destroy())
        self.pintar()
        self.mostrar('centro', encima=False)

    def pintar(self):
        self.tabla.vaciar()
        for id_, fecha, _tipo, descripcion, estado in self.app.historial.lista():
            self.tabla.anadir([datetime.datetime.fromtimestamp(fecha).strftime('%d/%m %H:%M'),
                               self.ESTADOS.get(estado, estado), descripcion], (id_, estado, descripcion),
                              etiqueta='aviso' if estado == 'error' else 'gris' if estado == 'deshecho' else None)
        self.tabla.ajustar()
        self._botones()

    def _botones(self):
        elegido = self.tabla.elegidos()
        self.b_deshacer.configure(state='normal' if elegido and elegido[0][1] == 'hecho' else 'disabled')
        self.b_ver.configure(state='normal' if elegido else 'disabled')

    def _deshacer(self):
        for id_, estado, _ in self.tabla.elegidos():
            if estado == 'hecho':
                self.app.deshacer(id_, al_terminar=self.pintar)

    def _ver(self, valor=None):
        elegido = [valor] if valor else self.tabla.elegidos()
        if elegido:
            id_, _, descripcion = elegido[0]
            VentanaArchivos(self, self.app, descripcion, self.app.historial.pasos(id_)[0])


class VentanaArchivos(Ventana):
    """Cada archivo de una acción del historial, con su ruta entera. Doble clic: mostrarlo en el Explorador."""
    QUE = {'mover': 'Movido', 'papelera': 'A la Papelera', 'crear_carpeta': 'Carpeta nueva', 'extraer': 'Descomprimido'}

    def __init__(self, padre, app, descripcion: str, pasos: list[dict]):
        super().__init__(padre, 'Archivos', redimensionable=True)
        cfg = app.cfg
        cuerpo = ctk.CTkFrame(self, fg_color='transparent')
        cuerpo.pack(fill='both', expand=True, padx=16, pady=14)
        ctk.CTkLabel(cuerpo, text=descripcion, font=fuente(12), anchor='w', justify='left',
                     wraplength=760).pack(fill='x', pady=(0, 8))
        tabla = TablaRutas(cuerpo, [('Qué', 100), ('Archivo', 240), ('Carpeta', 260), ('Antes estaba en', 160)],
                           alto=14, al_abrir=mostrar_en_explorador)
        tabla.pack(fill='both', expand=True)
        for p in pasos:
            que = self.QUE.get(p.get('op'), p.get('op', ''))
            if p.get('op') == 'mover':
                tabla.anadir([que, os.path.basename(p['a']), carpeta_corta(cfg, p['a']), cfg.relativa(p['de'])], p['a'])
            elif p.get('op') == 'extraer':
                for f in p.get('archivos', []):
                    tabla.anadir([que, os.path.basename(f), carpeta_corta(cfg, f), os.path.basename(p['zip'])], f)
            elif p.get('ruta'):
                nombre = os.path.basename(p['ruta']) + (os.sep if p.get('op') == 'crear_carpeta' else '')
                tabla.anadir([que, nombre, carpeta_corta(cfg, p['ruta']), ''], p['ruta'])
        if not pasos:
            tabla.anadir(['', 'Esta acción no tiene archivos que enseñar', '', ''])
        tabla.ajustar()
        ctk.CTkLabel(cuerpo, text='Doble clic en una fila: abrir su carpeta en el Explorador.', font=fuente(11),
                     text_color=GRIS, anchor='w').pack(fill='x', pady=(6, 0))
        _boton_secundario(cuerpo, 'Cerrar', self.destroy).pack(side='right', pady=(8, 0))
        self.bind('<Escape>', lambda e: self.destroy())
        self.mostrar('centro', padre, encima=False)
