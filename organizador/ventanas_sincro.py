"""Ventanas del sincronizador: confirmar (o deshacer) un borrado masivo, y PDF que parecen definitivos."""
import os

import customtkinter as ctk

from .ventanas import GRIS, ROJO, TablaRutas, Ventana, fuente, mostrar_en_explorador

ABIERTAS_HASTA = 200           # con más archivos, las carpetas salen cerradas (se abren con un clic)


def grupos_borrados(retenidos: list[tuple[str, list[str]]]) -> list[tuple[str, list[tuple[str, list[str]]]]]:
    """Los borrados retenidos por carpeta: [(carpeta, [(nombre, sitios donde falta)])], todo en orden."""
    grupos: dict[str, list[tuple[str, list[str]]]] = {}
    for ruta, donde in retenidos:
        grupos.setdefault(os.path.dirname(ruta), []).append((os.path.basename(ruta), list(donde)))
    return [(c, sorted(archivos, key=lambda x: x[0].casefold()))
            for c, archivos in sorted(grupos.items(), key=lambda x: x[0].casefold())]


class VentanaBorrados(Ventana):
    """La sincronización se ha parado porque iba a mandar a la papelera muchos archivos."""

    def __init__(self, app, retenidos: list[tuple[str, list[str]]]):
        super().__init__(app.root, 'Sincronización en pausa', redimensionable=True)
        self.app, self.retenidos = app, retenidos
        n = len(retenidos)
        sitios = sorted({s for _, donde in retenidos for s in donde})
        cuerpo = ctk.CTkFrame(self, fg_color='transparent')
        cuerpo.pack(fill='both', expand=True, padx=18, pady=14)
        ctk.CTkLabel(cuerpo, text='La sincronización se ha parado', font=fuente(16, True), anchor='w').pack(fill='x')
        ctk.CTkLabel(cuerpo, text=f'Han desaparecido {n} archivos de {" y ".join(sitios) or "una copia"} que siguen en los '
                                  f'demás sitios. Son más de {app.cfg.max_borrados}, así que no he tocado nada hasta que '
                                  'decidas. Si los borraste tú, mándalos a la papelera también en los demás sitios; si no '
                                  'sabes qué ha pasado, recupéralos. Doble clic en un archivo: verlo en el Explorador '
                                  '(donde aún está).',
                     font=fuente(12), text_color=GRIS, anchor='w', justify='left', wraplength=660).pack(fill='x', pady=(2, 8))
        # Una lista de ttk (no una fila de widgets por archivo): se abre al instante aunque sean miles.
        tabla = TablaRutas(cuerpo, [('Carpeta y archivos', 640)], alto=14, arbol=True, al_abrir=self._mostrar)
        tabla.pack(fill='both', expand=True)
        grupos = grupos_borrados(retenidos)
        for carpeta, archivos in grupos:
            faltan = sorted({s for _, donde in archivos for s in donde})
            padre = tabla.anadir([f'{carpeta or "(carpeta principal)"}{os.sep}    ({len(archivos)} · falta en '
                                  f'{", ".join(faltan)})'],
                                 abierta=n <= ABIERTAS_HASTA or len(grupos) == 1, etiqueta='carpeta')
            for nombre, donde in archivos:
                distinto = sorted(donde) != faltan
                tabla.anadir([nombre + (f'    (falta en {", ".join(donde)})' if distinto else '')],
                             os.path.join(carpeta, nombre), padre=padre)
        tabla.ajustar()
        botones = ctk.CTkFrame(cuerpo, fg_color='transparent')
        botones.pack(fill='x', pady=(10, 0))
        ctk.CTkButton(botones, text='Recuperarlos', width=150, font=fuente(13, True),
                      command=lambda: self._decidir('recuperar')).pack(side='left')
        ctk.CTkButton(botones, text='Mandarlos a la papelera en todos', width=240, fg_color=ROJO,
                      hover_color=('#9E1F1F', '#D45555'), command=lambda: self._decidir('borrar')).pack(side='left', padx=8)
        ctk.CTkButton(botones, text='Más tarde', width=100, fg_color='transparent', border_width=1,
                      text_color=('gray10', 'gray90'), command=self.destroy).pack(side='right')
        self.bind('<Escape>', lambda e: self.destroy())
        self.mostrar('centro')

    def _decidir(self, accion):
        self.destroy()
        self.app.decidir_borrados(self.retenidos, accion)

    def _mostrar(self, rel):
        """En el Explorador, en el sitio donde aún está (OneDrive, G: o H:)."""
        raices = [self.app.cfg.onedrive] + [c['raiz'] for c in self.app.cfg.copias]
        ruta = next((os.path.join(r, rel) for r in raices if os.path.exists(os.path.join(r, rel))),
                    os.path.join(self.app.cfg.onedrive, rel))
        mostrar_en_explorador(ruta)


class VentanaPDF(Ventana):
    """Un PDF parece la versión definitiva de un Google Doc: ¿se borra el Doc editable?"""

    def __init__(self, app, casos: list[tuple[str, str, str]]):
        super().__init__(app.root, 'Versión definitiva en PDF')
        self.app = app
        cuerpo = ctk.CTkFrame(self, fg_color='transparent')
        cuerpo.pack(fill='both', expand=True, padx=18, pady=14)
        ctk.CTkLabel(cuerpo, text='¿Versión definitiva?', font=fuente(16, True), anchor='w').pack(fill='x')
        ctk.CTkLabel(cuerpo, text='Estos PDF tienen el mismo nombre (o el mismo texto) que un Google Doc de su carpeta. '
                                  'Si el PDF es la versión definitiva, el Doc editable sobra. Si lo borras, va a la '
                                  'papelera de Drive (y su Word, a la Papelera).',
                     font=fuente(12), text_color=GRIS, anchor='w', justify='left', wraplength=600).pack(fill='x', pady=(2, 8))
        for ruta, id_, nombre in casos:
            f = ctk.CTkFrame(cuerpo)
            f.pack(fill='x', pady=4)
            ctk.CTkLabel(f, text=f'«{os.path.basename(ruta)}» parece la versión definitiva de «{nombre}».\n'
                                 f'En {os.path.dirname(app.cfg.relativa(ruta))}',
                         font=fuente(12), anchor='w', justify='left', wraplength=600).pack(fill='x', padx=10, pady=(8, 4))
            b = ctk.CTkFrame(f, fg_color='transparent')
            b.pack(fill='x', padx=10, pady=(0, 8))
            ctk.CTkButton(b, text='Conservar el Doc', width=150,
                          command=lambda r=ruta, w=f: self._decidir(r, None, w)).pack(side='left')
            ctk.CTkButton(b, text='Borrar el Doc', width=150, fg_color=ROJO, hover_color=('#9E1F1F', '#D45555'),
                          command=lambda r=ruta, i=id_, w=f: self._decidir(r, i, w)).pack(side='left', padx=8)
        ctk.CTkButton(cuerpo, text='Más tarde', width=100, fg_color='transparent', border_width=1,
                      text_color=('gray10', 'gray90'), command=self.destroy).pack(side='right', pady=(8, 0))
        self.bind('<Escape>', lambda e: self.destroy())
        self.mostrar('centro')

    def _decidir(self, ruta, id_, fila):
        if id_:
            self.app.borrar_doc(id_, ruta)
        else:
            self.app.conservar_doc(ruta)
        fila.destroy()
        if not [w for w in self.winfo_children()[0].winfo_children() if isinstance(w, ctk.CTkFrame)]:
            self.destroy()
