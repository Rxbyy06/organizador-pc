"""Ventana semanal (los lunes): pestaña «Resumen» y pestaña «Capturas»; y el diálogo «Guardar en…»."""
import datetime
import os

import customtkinter as ctk

from .nombres import libre, ruta_valida, sanear
from .revision import fecha_de, miniatura, nombre_sugerido
from .ventanas import (GRIS, NARANJA, ROJO, VERDE, TablaRutas, Ventana, _corto, _tam, carpeta_corta, elegir_carpeta,
                       fuente, mostrar_en_explorador, ruta_bonita)


class PanelCapturas(ctk.CTkFrame):
    """Cuadrícula de capturas. Cada una: Borrar (lo marcado de entrada), Guardar en… o Dejar."""
    COLUMNAS, LADO = 4, 220
    OPCIONES = ['Borrar', 'Guardar en…', 'Dejar']

    def __init__(self, padre, app, rutas: list[str]):
        super().__init__(padre, fg_color='transparent')
        self.app, self.rutas = app, rutas
        # Las que ya dejó otra semana salen como «Dejar»; las demás, como «Borrar».
        self.eleccion: dict[str, str] = {r: 'Dejar' if app.revision.dejada(r) else 'Borrar' for r in rutas}
        self.destino: dict[str, tuple[str, str]] = {}
        self.celdas: dict[str, dict] = {}
        self.imagenes = []                              # que tkinter no las suelte
        n = len(rutas)
        ctk.CTkLabel(self, text=f'{n} {"capturas o grabaciones" if n != 1 else "captura o grabación"} de más de '
                                f'{app.cfg.dias_capturas:g} días. De entrada van a la Papelera: cambia solo las que '
                                'quieras guardar o dejar. Doble clic en una miniatura para verla en grande.',
                     font=fuente(12), text_color=GRIS, anchor='w', justify='left',
                     wraplength=self.COLUMNAS * (self.LADO + 24)).pack(fill='x', pady=(0, 8))
        self.lista = ctk.CTkScrollableFrame(self, width=self.COLUMNAS * (self.LADO + 24), height=470)
        self.lista.pack(fill='both', expand=True)
        for i, ruta in enumerate(rutas):
            self._celda(ruta, i // self.COLUMNAS, i % self.COLUMNAS)
        self.l_resumen = ctk.CTkLabel(self, text='', font=fuente(13, True), anchor='w')
        self.l_resumen.pack(fill='x', pady=(8, 0))
        self._resumen()
        self.abierta = True                             # al cerrar la ventana, las miniaturas que falten no se hacen
        self.bind('<Destroy>', lambda e: e.widget is self and setattr(self, 'abierta', False), add='+')
        app.ejecutar(self._cargar_miniaturas, que='preparar las miniaturas')

    def _celda(self, ruta, fila, col):
        f = ctk.CTkFrame(self.lista, width=self.LADO + 12)
        f.grid(row=fila, column=col, padx=6, pady=6, sticky='n')
        img = ctk.CTkLabel(f, text='…', width=self.LADO, height=int(self.LADO * 0.62), fg_color=('gray80', 'gray25'))
        img.pack(padx=6, pady=(6, 2))
        img.bind('<Double-Button-1>', lambda e: os.startfile(ruta))
        nombre = os.path.basename(ruta).replace('Captura de pantalla ', '')      # la fecha ya va debajo
        ctk.CTkLabel(f, text=_corto(nombre, 30), font=fuente(11), anchor='w').pack(fill='x', padx=6)
        info = f'{datetime.datetime.fromtimestamp(fecha_de(ruta)):%d/%m/%Y} · {_tam(os.path.getsize(ruta))}'
        if desde := self.app.revision.dejada(ruta):
            info += f' · dejada el {datetime.datetime.fromtimestamp(desde):%d/%m}'
        ctk.CTkLabel(f, text=info, font=fuente(10), text_color=GRIS, anchor='w').pack(fill='x', padx=6)
        seg = ctk.CTkSegmentedButton(f, values=self.OPCIONES, font=fuente(11),
                                     command=lambda v, r=ruta: self._elegir(r, v))
        seg.set(self.eleccion[ruta])
        seg.pack(fill='x', padx=6, pady=(4, 2))
        nota = ctk.CTkLabel(f, text='', font=fuente(10), text_color=VERDE, anchor='w', justify='left',
                            wraplength=self.LADO)
        nota.pack(fill='x', padx=6, pady=(0, 6))
        self.celdas[ruta] = {'img': img, 'seg': seg, 'nota': nota}

    def _cargar_miniaturas(self):
        """(en segundo plano) Unos 0,4 s por captura; van apareciendo según están."""
        for ruta in self.rutas:
            if not self.abierta:
                return
            im = miniatura(ruta, self.LADO)
            self.app.en_ui(lambda r=ruta, im=im: self._poner_miniatura(r, im))

    def _poner_miniatura(self, ruta, im):
        if not self.winfo_exists():
            return
        ci = ctk.CTkImage(light_image=im, dark_image=im, size=im.size)
        self.imagenes.append(ci)
        self.celdas[ruta]['img'].configure(image=ci, text='', fg_color='transparent')

    def _elegir(self, ruta, valor):
        anterior = self.eleccion[ruta]
        if valor == 'Guardar en…':
            def hecho(destino):
                if destino:
                    self.eleccion[ruta], self.destino[ruta] = valor, destino
                    self.celdas[ruta]['nota'].configure(
                        text='→ ' + ruta_bonita(self.app.cfg, destino[0]) + '  ›  ' + destino[1])
                else:
                    self.celdas[ruta]['seg'].set(anterior)
                self._resumen()
            DialogoGuardar(self.winfo_toplevel(), self.app, ruta, hecho)
            return
        self.eleccion[ruta] = valor
        self.destino.pop(ruta, None)
        self.celdas[ruta]['nota'].configure(text='')
        self._resumen()

    def _resumen(self):
        c = {o: sum(1 for v in self.eleccion.values() if v == o) for o in self.OPCIONES}
        b, g, d = c['Borrar'], c['Guardar en…'], c['Dejar']
        self.l_resumen.configure(text=f'{b} a la Papelera  ·  {g} se guarda{"n" if g != 1 else ""}  ·  '
                                      f'{d} se queda{"n" if d != 1 else ""}')

    def elecciones(self):
        borrar = [r for r, v in self.eleccion.items() if v == 'Borrar']
        guardar = [(r, *self.destino[r]) for r, v in self.eleccion.items() if v == 'Guardar en…']
        dejar = [r for r, v in self.eleccion.items() if v == 'Dejar']
        return borrar, guardar, dejar


class PanelResumen(ctk.CTkScrollableFrame):
    """Lo que ha hecho el programa en la semana, conflictos, duplicados nuevos, espacio y lo pendiente."""

    def __init__(self, padre, app, d):
        super().__init__(padre, width=960, height=520, fg_color='transparent')
        self.app, self.d = app, d
        hasta = datetime.date.today()
        desde = datetime.date.fromtimestamp(d.desde)
        self._titulo(f'Del {desde:%d/%m} al {hasta:%d/%m}')

        self._seccion('Sincronización')
        sitios = sorted(set(d.copiados) | set(d.movidos))
        partes = [f'{s} {d.copiados[s]} copiados, {d.movidos[s]} movidos o renombrados' for s in sitios]
        self._linea(f'{d.pasadas} pasadas. ' + ('; '.join(partes) if partes else 'Sin cambios que repartir.') +
                    (f' {d.a_papelera} a la papelera.' if d.a_papelera else ''))
        repetidos = [(m, n) for m, n in d.errores.items() if n >= 3]
        for m, n in repetidos:
            self._linea(f'Se repite ({n} veces): {m}', NARANJA)
        if d.conflictos:
            self._seccion(f'Conflictos ({len(d.conflictos)}): se guardaron las dos versiones')
            self._tabla([os.path.join(app.cfg.onedrive, r) for r in d.conflictos])
            self._linea('Doble clic en uno: abrir su carpeta en el Explorador.', GRIS)

        w = d.words
        if any(w.values()):
            self._seccion('Copias Word de los Docs')
            self._linea(f'{w["nuevos"]} nuevas, {w["actualizados"]} actualizadas, {w["movidos"]} movidas, '
                        f'{w["a_papelera"]} a la papelera.' +
                        (f' {w["editados"]} editadas a mano y apartadas.' if w['editados'] else ''),
                        NARANJA if w['editados'] else None)

        a = d.acciones
        self._seccion('Organizador')
        self._linea(f'{a["mover"]} descargas organizadas, {a["descartar"]} descartadas, '
                    f'{a["limpieza"]} limpiezas de Descargas.')

        if d.duplicados:
            n = len(d.duplicados)
            self._seccion(f'Duplicados ({n} grupo{"s" if n != 1 else ""})')
            self._linea('Marca la copia que sobra y pulsa «A la papelera» (doble clic: abrir su carpeta).', GRIS)
            for g in d.duplicados:
                caja = ctk.CTkFrame(self)
                caja.pack(fill='x', pady=4)
                titulo = 'DUDOSO: mismo texto, distinto archivo' if g.casi else 'Idénticos'
                cab = ctk.CTkFrame(caja, fg_color='transparent')
                cab.pack(fill='x', padx=8, pady=(6, 0))
                ctk.CTkLabel(cab, text=titulo, font=fuente(11, True), anchor='w').pack(side='left')
                ctk.CTkButton(cab, text='No volver a avisar', width=140, height=24, fg_color='transparent',
                              border_width=1, text_color=('gray10', 'gray90'),
                              command=lambda g=g, c=caja: (app.resumen.ignorar(g), c.destroy())).pack(side='right')
                tabla = self._tabla(g.rutas, caja, varias=True)
                pie = ctk.CTkFrame(caja, fg_color='transparent')
                pie.pack(fill='x', padx=8, pady=(4, 8))
                nota = ctk.CTkLabel(pie, text='', font=fuente(11), text_color=NARANJA, anchor='w')
                ctk.CTkButton(pie, text='A la papelera', width=130, height=26, font=fuente(11), fg_color=ROJO,
                              hover_color=('#9E1F1F', '#D45555'),
                              command=lambda t=tabla, n=nota: self._tirar(t, n)).pack(side='left')
                nota.pack(side='left', padx=10)

        self._seccion('Espacio')
        for u in d.espacio:
            self._linea(u.texto(), NARANJA if u.aviso else None)
        if d.pendientes:
            self._seccion('Pendiente')
            for p in d.pendientes:
                self._linea(p, NARANJA)

    def _titulo(self, t):
        ctk.CTkLabel(self, text=t, font=fuente(14, True), anchor='w').pack(fill='x', pady=(0, 4))

    def _seccion(self, t):
        ctk.CTkLabel(self, text=t, font=fuente(13, True), anchor='w').pack(fill='x', pady=(12, 2))

    def _linea(self, t, color=None):
        ctk.CTkLabel(self, text=t, font=fuente(12), anchor='w', justify='left', wraplength=920,
                     text_color=color or ('gray10', 'gray90')).pack(fill='x')

    def _tabla(self, rutas, padre=None, varias=False) -> TablaRutas:
        """Los archivos con su ruta entera (nombre y carpeta) y barra horizontal si no caben."""
        t = TablaRutas(padre or self, [('Archivo', 300), ('Carpeta', 560)], alto=min(len(rutas), 8),
                       al_abrir=mostrar_en_explorador, varias=varias)
        for r in rutas:
            t.anadir([os.path.basename(r), carpeta_corta(self.app.cfg, r)], r)
        t.ajustar()
        t.pack(fill='x', padx=8, pady=(2, 0))
        return t

    def _tirar(self, tabla: TablaRutas, nota):
        """Las copias marcadas de un grupo de duplicados, a la Papelera. Siempre queda al menos una."""
        marcadas = tabla.elegidas()
        if not marcadas:
            nota.configure(text='Marca primero la copia que sobra.')
            return
        if len(marcadas) >= len(tabla.valores):
            nota.configure(text='Deja al menos una copia: no mando todas a la papelera.')
            return
        for iid in marcadas:
            self.app.tirar_duplicado(tabla.valores[iid])
            tabla.quitar(iid)
        nota.configure(text=f'{len(marcadas)} a la papelera (se recupera de allí).')


class VentanaSemanal(Ventana):
    """La ventana de los lunes: «Resumen» y, si hay capturas viejas, «Capturas»."""

    def __init__(self, app, datos, capturas: list[str]):
        super().__init__(app.root, 'Revisión semanal')
        self.app, self.datos = app, datos
        cuerpo = ctk.CTkFrame(self, fg_color='transparent')
        cuerpo.pack(fill='both', expand=True, padx=16, pady=12)
        ctk.CTkLabel(cuerpo, text='Revisión semanal', font=fuente(16, True), anchor='w').pack(fill='x')
        self.pestanas = pestanas = ctk.CTkTabview(cuerpo, width=1000, height=600)
        pestanas.pack(fill='both', expand=True)
        self.resumen = PanelResumen(pestanas.add('Resumen'), app, datos)
        self.resumen.pack(fill='both', expand=True)
        self.capturas = None
        if capturas:
            nombre = f'Capturas ({len(capturas)})'
            self.capturas = PanelCapturas(pestanas.add(nombre), app, capturas)
            self.capturas.pack(fill='both', expand=True)
        pie = ctk.CTkFrame(cuerpo, fg_color='transparent')
        pie.pack(fill='x', pady=(10, 0))
        ctk.CTkButton(pie, text='Más tarde', width=110, fg_color='transparent', border_width=1,
                      text_color=('gray10', 'gray90'), command=self.mas_tarde).pack(side='right')
        ctk.CTkButton(pie, text='Aplicar y cerrar' if capturas else 'Cerrar', width=140, font=fuente(13, True),
                      command=self.aplicar).pack(side='right', padx=8)
        self.protocol('WM_DELETE_WINDOW', self.mas_tarde)
        self.bind('<Escape>', lambda e: self.mas_tarde())
        self.mostrar('centro')
        self.after(400, lambda: self.winfo_exists() and self.attributes('-topmost', False))

    def aplicar(self):
        borrar, guardar, dejar = self.capturas.elecciones() if self.capturas else ([], [], [])
        self.destroy()
        self.app.aplicar_semana(self.datos, borrar, guardar, dejar)

    def mas_tarde(self):
        self.destroy()
        self.app.posponer_revision()


class DialogoGuardar(Ventana):
    """Dónde guardar una captura: carpeta (con «Cambiar…») y nombre."""

    def __init__(self, padre, app, ruta, al_terminar):
        super().__init__(padre, 'Guardar captura')
        self.app, self.al_terminar = app, al_terminar
        self.carpeta = app.ultima_carpeta_captura or app.cfg.onedrive
        base, self.ext = os.path.splitext(nombre_sugerido(ruta))
        cuerpo = ctk.CTkFrame(self, fg_color='transparent')
        cuerpo.pack(fill='both', expand=True, padx=18, pady=14)
        ctk.CTkLabel(cuerpo, text='Carpeta', font=fuente(12, True), anchor='w').pack(fill='x')
        fila = ctk.CTkFrame(cuerpo, fg_color='transparent')
        fila.pack(fill='x')
        self.l_carpeta = ctk.CTkLabel(fila, text='', font=fuente(), anchor='w', justify='left', wraplength=380)
        self.l_carpeta.pack(side='left', fill='x', expand=True)
        ctk.CTkButton(fila, text='Cambiar…', width=96, command=self.cambiar).pack(side='right')
        ctk.CTkLabel(cuerpo, text='Nombre', font=fuente(12, True), anchor='w').pack(fill='x', pady=(10, 0))
        fila = ctk.CTkFrame(cuerpo, fg_color='transparent')
        fila.pack(fill='x')
        self.e_nombre = ctk.CTkEntry(fila, font=fuente(), width=380, height=32)
        self.e_nombre.insert(0, base)
        self.e_nombre.pack(side='left', fill='x', expand=True)
        ctk.CTkLabel(fila, text=self.ext, font=fuente(), text_color=GRIS).pack(side='left', padx=(6, 0))
        self.l_error = ctk.CTkLabel(cuerpo, text='', font=fuente(11), text_color=ROJO, anchor='w')
        self.l_error.pack(fill='x')
        botones = ctk.CTkFrame(cuerpo, fg_color='transparent')
        botones.pack(fill='x', pady=(8, 0))
        ctk.CTkButton(botones, text='Guardar aquí', width=130, command=self.guardar).pack(side='left')
        ctk.CTkButton(botones, text='Cancelar', width=100, fg_color='transparent', border_width=1,
                      text_color=('gray10', 'gray90'), command=self.cancelar).pack(side='left', padx=8)
        self.protocol('WM_DELETE_WINDOW', self.cancelar)
        self.bind('<Return>', lambda e: self.guardar())
        self.bind('<Escape>', lambda e: self.cancelar())
        self._pintar()
        self.mostrar('centro', padre)
        self.grab_set()

    def _pintar(self):
        self.l_carpeta.configure(text=ruta_bonita(self.app.cfg, self.carpeta))

    def cambiar(self):
        carpeta = elegir_carpeta(self, self.carpeta, '¿Dónde guardo la captura?')
        if not self.winfo_exists():
            return
        if carpeta:
            self._elegida(carpeta)
        self.lift()
        self.grab_set()

    def _elegida(self, carpeta):
        self.carpeta = carpeta
        self._pintar()
        self.grab_set()

    def guardar(self):
        nombre = sanear(self.e_nombre.get().strip())
        if err := ruta_valida(os.path.join(self.carpeta, nombre + self.ext)):
            self.l_error.configure(text=f'No vale: {err}')
            return
        nombre = libre(self.carpeta, nombre, self.ext)
        self.app.ultima_carpeta_captura = self.carpeta
        self.grab_release()
        self.destroy()
        self.al_terminar((self.carpeta, nombre + self.ext))

    def cancelar(self):
        self.grab_release()
        self.destroy()
        self.al_terminar(None)
