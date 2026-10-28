"""Las ventanas con listas de rutas: se abren, enseñan cada nombre entero y se desplazan en horizontal.

    python -m unittest tests.test_ventanas

Abre ventanas de verdad (un momento) con datos de mentira.
"""
import os
import shutil
import sys
import tempfile
import time
import types
import unittest
from collections import Counter
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import customtkinter as ctk

from organizador import tk_hilos
from organizador.config import Config
from organizador.resumen import DatosResumen, Grupo
from organizador.ventanas import TablaRutas, VentanaArchivos, VentanaHistorial, VentanaPendientes, existente
from organizador.ventanas_revision import PanelResumen
from organizador.ventanas_sincro import VentanaBorrados

SEP = os.sep
LARGO = 'Apunts del tema 7 - Distribucions de probabilitat contínues i teorema del límit central (versió revisada)'


class Ventanas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tk_hilos.instalar()
        cls.root = ctk.CTk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='ventanas')
        self.cfg = Config(descargas=os.path.join(self.tmp, 'Descargas'), onedrive=os.path.join(self.tmp, 'OneDrive'),
                          universidad='U', datos=self.tmp, copias=[{'nombre': 'H:', 'raiz': os.path.join(self.tmp, 'H'),
                                                                    'carpetas': ['U']}])
        self.app = types.SimpleNamespace(root=self.root, cfg=self.cfg)
        self.abiertas = []

    def tearDown(self):
        for v in self.abiertas:
            if v.winfo_exists():
                v.destroy()
        self.root.update()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def abrir(self, clase, *args):
        v = clase(*args)
        self.abiertas.append(v)
        for _ in range(8):                  # que acabe de colocarse (se recoloca a los 60 y 250 ms)
            self.root.update()
            time.sleep(0.05)
        self.assertEqual(v.state(), 'normal')          # visible (customtkinter puede dejarla oculta)
        return v

    def tablas(self, w):
        res = []
        for h in w.winfo_children():
            res += ([h] if isinstance(h, TablaRutas) else []) + self.tablas(h)
        return res

    def textos(self, tabla):
        res, pila = [], list(tabla.t.get_children())
        while pila:
            iid = pila.pop(0)
            item = tabla.t.item(iid)
            res.append([item['text']] + [str(v) for v in item['values']])
            pila += tabla.t.get_children(iid)
        return res

    def test_borrados_miles_con_cada_nombre_y_rapida(self):
        ret = [(f'U{SEP}Asignatura{SEP}Prácticas{SEP}{i:04d} {LARGO}.pdf', ['H:']) for i in range(6633)]
        t0 = time.monotonic()
        v = self.abrir(VentanaBorrados, self.app, ret)
        self.assertLess(time.monotonic() - t0, 5)
        tabla = self.tablas(v)[0]
        filas = self.textos(tabla)
        self.assertEqual(len(filas), 6634)                                # la carpeta y sus 6633 archivos
        self.assertIn('(6633 · falta en H:)', filas[0][0])
        self.assertEqual(filas[1][0], f'0000 {LARGO}.pdf')                # el nombre entero, no «…»
        self.assertGreater(tabla.t.column('#0', 'width'), tabla.t.winfo_width())   # no cabe: barra horizontal
        tabla.t.xview_moveto(1.0)
        self.root.update()
        self.assertGreater(tabla.t.xview()[0], 0)                          # y se desplaza

    def test_borrados_pocos_salen_abiertos_y_se_ven_en_el_explorador(self):
        ruta = os.path.join(self.tmp, 'H', 'U', 'x.pdf')
        os.makedirs(os.path.dirname(ruta))
        open(ruta, 'w').close()
        v = self.abrir(VentanaBorrados, self.app, [(f'U{SEP}x.pdf', ['OneDrive']), (f'U{SEP}y.pdf', ['OneDrive', 'G:'])])
        tabla = self.tablas(v)[0]
        carpeta = tabla.t.get_children()[0]
        self.assertTrue(tabla.t.item(carpeta, 'open'))
        self.assertEqual([f[0] for f in self.textos(tabla)[1:]], ['x.pdf    (falta en OneDrive)', 'y.pdf'])
        with mock.patch('organizador.ventanas_sincro.mostrar_en_explorador') as mostrar:
            tabla._abrir(tabla.t.get_children(carpeta)[0])
        mostrar.assert_called_once_with(ruta)                              # donde aún está: H:

    def test_pendientes(self):
        os.makedirs(self.cfg.descargas)
        largo = os.path.join(self.cfg.descargas, LARGO + '.pdf')
        corto = os.path.join(self.cfg.descargas, 'a.zip')
        self.app.pendientes = lambda: [(largo, time.time() - 6 * 86400, 3600), (corto, time.time(), 6 * 86400)]
        self.app.organizar = mock.Mock()
        for r in (largo, corto):
            open(r, 'w').close()
        v = self.abrir(VentanaPendientes, self.app)
        tabla = self.tablas(v)[0]
        filas = self.textos(tabla)
        self.assertEqual(filas[0][1:], ['mañana', filas[0][2], LARGO + '.pdf'])     # lo corto primero; el nombre, entero
        self.assertIn('aviso', tabla.t.item(tabla.t.get_children()[0], 'tags'))
        tabla._abrir(tabla.t.get_children()[1])                            # doble clic: organizar
        self.app.organizar.assert_called_once_with(corto)

    def test_historial_y_sus_archivos(self):
        de = os.path.join(self.cfg.descargas, 'tema7.pdf')
        a = os.path.join(self.cfg.onedrive, 'U', 'Asignatura', '1 - Teoría', LARGO + '.pdf')
        pasos = [{'op': 'crear_carpeta', 'ruta': os.path.dirname(a)}, {'op': 'mover', 'de': de, 'a': a},
                 {'op': 'papelera', 'ruta': os.path.join('H:' + SEP, 'Mi unidad', 'U', 'viejo.pdf')}]
        self.app.historial = types.SimpleNamespace(
            lista=lambda: [(1, time.time(), 'mover', f'Movido «tema7.pdf» → U\\{LARGO}.pdf', 'hecho'),
                           (2, time.time(), 'sincro', 'Sincronización: 1 a la papelera', 'deshecho')],
            pasos=lambda id_: (pasos, 'hecho'))
        self.app.deshacer = mock.Mock()
        v = self.abrir(VentanaHistorial, self.app)
        tabla = self.tablas(v)[0]
        self.assertEqual([f[2] for f in self.textos(tabla)], ['hecho', 'deshecho'])
        self.assertEqual(str(v.b_deshacer.cget('state')), 'disabled')      # sin nada marcado
        tabla.t.selection_set(tabla.t.get_children()[1])
        self.root.update()
        self.assertEqual(str(v.b_deshacer.cget('state')), 'disabled')      # lo deshecho no se deshace otra vez
        tabla.t.selection_set(tabla.t.get_children()[0])
        self.root.update()
        v._deshacer()
        self.app.deshacer.assert_called_once()
        with mock.patch('organizador.ventanas.VentanaArchivos') as ver:
            v._ver()
        ver.assert_called_once()
        archivos = self.abrir(VentanaArchivos, v, self.app, 'Movido…', pasos)
        filas = self.textos(self.tablas(archivos)[0])
        self.assertEqual([f[1] for f in filas], ['Carpeta nueva', 'Movido', 'A la Papelera'])
        self.assertEqual(filas[1][2:4], [LARGO + '.pdf', f'U{SEP}Asignatura{SEP}1 - Teoría'])
        self.assertEqual(filas[1][4], de)                                  # de dónde venía (fuera de OneDrive)

    def test_resumen_conflictos_y_duplicados(self):
        uno = os.path.join(self.cfg.onedrive, 'U', 'A', LARGO + '.pdf')
        dos = os.path.join(self.cfg.onedrive, 'U', 'B', LARGO + '.pdf')
        d = DatosResumen(time.time() - 7 * 86400, copiados=Counter(), movidos=Counter(),
                         conflictos=[f'U{SEP}A{SEP}x (conflicto 2026-10-27).docx'], duplicados=[Grupo('h', [uno, dos])])
        self.app.resumen = mock.Mock()
        self.app.tirar_duplicado = mock.Mock()
        ventana = self.abrir(ctk.CTkToplevel, self.root)
        panel = PanelResumen(ventana, self.app, d)
        panel.pack()
        self.root.update()
        conflictos, duplicados = self.tablas(panel)
        self.assertEqual(self.textos(conflictos)[0][1:], ['x (conflicto 2026-10-27).docx', f'U{SEP}A'])
        self.assertEqual([f[2] for f in self.textos(duplicados)], [f'U{SEP}A', f'U{SEP}B'])
        nota = mock.Mock()
        panel._tirar(duplicados, nota)                                     # nada marcado
        self.app.tirar_duplicado.assert_not_called()
        duplicados.t.selection_set(duplicados.t.get_children())
        panel._tirar(duplicados, nota)                                     # las dos: no, siempre queda una
        self.app.tirar_duplicado.assert_not_called()
        duplicados.t.selection_set(duplicados.t.get_children()[1])
        panel._tirar(duplicados, nota)
        self.app.tirar_duplicado.assert_called_once_with(dos)
        self.assertEqual(len(duplicados.t.get_children()), 1)

    def test_selector_abre_en_lo_mas_cercano_que_existe(self):
        os.makedirs(os.path.join(self.cfg.onedrive, 'U'))
        self.assertEqual(existente(os.path.join(self.cfg.onedrive, 'U', 'nueva', 'otra')),
                         os.path.join(self.cfg.onedrive, 'U'))


if __name__ == '__main__':
    unittest.main()
