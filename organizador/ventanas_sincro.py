"""Ventana del sincronizador: confirmar (o deshacer) un borrado masivo."""
import os

import customtkinter as ctk

from .ventanas import GRIS, ROJO, Ventana, _corto, fuente


def lineas_borrados(retenidos: list[tuple[str, list[str]]]) -> list[str]:
    """Los borrados retenidos, agrupados por carpeta: «carpeta\\  ·  N archivos  ·  falta en G:, H:»."""
    grupos: dict[tuple[str, tuple[str, ...]], list[str]] = {}
    for ruta, donde in retenidos:
        grupos.setdefault((os.path.dirname(ruta), tuple(donde)), []).append(ruta)
    lineas = []
    for (carpeta, donde), rutas in sorted(grupos.items(), key=lambda x: x[0][0].casefold()):
        que = rutas[0] if len(rutas) == 1 else f'{carpeta}{os.sep}  ·  {len(rutas)} archivos'
        lineas.append(f'{que}  ·  falta en {", ".join(donde)}')
    return lineas


class VentanaBorrados(Ventana):
    """La sincronización se ha parado porque iba a mandar a la papelera muchos archivos."""

    def __init__(self, app, retenidos: list[tuple[str, list[str]]]):
        super().__init__(app.root, 'Sincronización en pausa')
        self.app, self.retenidos = app, retenidos
        n = len(retenidos)
        sitios = sorted({s for _, donde in retenidos for s in donde})
        cuerpo = ctk.CTkFrame(self, fg_color='transparent')
        cuerpo.pack(fill='both', expand=True, padx=18, pady=14)
        ctk.CTkLabel(cuerpo, text='La sincronización se ha parado', font=fuente(16, True), anchor='w').pack(fill='x')
        ctk.CTkLabel(cuerpo, text=f'Han desaparecido {n} archivos de {" y ".join(sitios) or "una copia"} que siguen en los '
                                  f'demás sitios. Son más de {app.cfg.max_borrados}, así que no he tocado nada hasta que '
                                  'decidas. Si los borraste tú, mándalos a la papelera también en los demás sitios; si no '
                                  'sabes qué ha pasado, recupéralos.',
                     font=fuente(12), text_color=GRIS, anchor='w', justify='left', wraplength=620).pack(fill='x', pady=(2, 8))
        # Un solo cuadro de texto (no una fila de widgets por archivo): se abre al instante aunque sean miles.
        lista = ctk.CTkTextbox(cuerpo, width=640, height=300, font=fuente(11), wrap='none')
        lista.pack(fill='both', expand=True)
        lista.insert('1.0', '\n'.join(lineas_borrados(retenidos)))
        lista.configure(state='disabled')
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


class VentanaPDF(Ventana):
    """Un PDF parece la versión definitiva de un Google Doc: ¿se borra el Doc editable?"""

    def __init__(self, app, casos: list[tuple[str, str, str]]):
        super().__init__(app.root, 'Versión definitiva en PDF')
        import os
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
            ctk.CTkLabel(f, text=f'«{_corto(os.path.basename(ruta), 50)}» parece la versión definitiva de «{nombre}».',
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
            self.app.words.decidir_pdf(ruta, 'conservar')
        fila.destroy()
        if not [w for w in self.winfo_children()[0].winfo_children() if isinstance(w, ctk.CTkFrame)]:
            self.destroy()
