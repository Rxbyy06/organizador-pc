"""Que el programa no se cuelgue: Tk desde otros hilos, icono y ventanas que nunca esperan a un candado.

    python -m unittest tests.test_hilos

La semana del 26-10-2026 se colgó nueve veces: el índice liberaba fuentes de ventanas ya cerradas (Tk)
con su candado cogido, mientras el icono pedía ese candado desde el hilo de las ventanas.
"""
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tkinter
import tkinter.font
import types
import unittest
from unittest import mock

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from organizador import app as A
from organizador import tk_hilos
from organizador.bandeja import Bandeja
from organizador.config import Config
from organizador.docs_word import Words
from organizador.huellas import Indice

# El cuelgue tal cual: un hilo con un candado cogido libera una fuente de Tk mientras la interfaz espera
# ese candado. El proceso se cierra solo a los 4 s y dice si la interfaz seguía viva.
CUELGUE = r'''
import gc, os, sys, threading, time, tkinter, tkinter.font
sys.path.insert(0, sys.argv[1])
from organizador import tk_hilos
root = tkinter.Tk(); root.withdraw()
tk_hilos.instalar()
candado, latido = threading.Lock(), [time.monotonic()]
class Ciclo: pass
c = Ciclo(); c.fuente = tkinter.font.Font(root, size=12); c.yo = c; nombre = c.fuente.name; del c
gc.disable()
def fondo():
    with candado:
        time.sleep(0.4)          # mientras, la interfaz se pone a esperar el candado
        gc.collect()             # la fuente se libera en este hilo, con el candado cogido
def ui():
    latido[0] = time.monotonic(); tk_hilos.vaciar()
    with candado:
        pass
    root.after(50, ui)
def vigia():
    time.sleep(4)
    vivo = time.monotonic() - latido[0] < 1
    queda = vivo and nombre in root.tk.call('font', 'names')
    print('VIVO' if vivo else 'COLGADO', 'QUEDA' if queda else 'LIBERADA', flush=True)
    os._exit(0)
root.after(100, lambda: threading.Thread(target=fondo, daemon=True).start())
root.after(50, ui)
threading.Thread(target=vigia, daemon=True).start()
root.mainloop()
'''


class TkDesdeOtroHilo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tk_hilos.instalar()
        cls.root = tkinter.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def nombres(self):
        return self.root.tk.call('font', 'names')

    def test_lo_que_suelta_otro_hilo_lo_libera_el_de_las_ventanas(self):
        caja = [tkinter.font.Font(self.root, size=11)]
        nombre = caja[0].name
        t = threading.Thread(target=caja.clear)        # la última referencia muere en otro hilo
        t.start()
        t.join(5)
        self.assertFalse(t.is_alive())
        self.assertIn(nombre, self.nombres())          # ese hilo no ha tocado Tk
        tk_hilos.vaciar()
        self.assertNotIn(nombre, self.nombres())       # el de las ventanas sí la ha liberado

    def test_en_el_hilo_de_las_ventanas_se_libera_al_momento(self):
        f = tkinter.font.Font(self.root, size=12)
        nombre = f.name
        del f
        self.assertNotIn(nombre, self.nombres())

    def test_variables_e_imagenes_tambien(self):
        caja = [tkinter.StringVar(self.root, 'x'), tkinter.PhotoImage(master=self.root, width=2, height=2)]
        var, img = str(caja[0]), caja[1].name
        t = threading.Thread(target=caja.clear)
        t.start()
        t.join(5)
        self.assertIn(img, self.root.tk.call('image', 'names'))
        tk_hilos.vaciar()
        self.assertNotIn(img, self.root.tk.call('image', 'names'))
        self.assertFalse(self.root.getboolean(self.root.tk.call('info', 'exists', var)))

    def test_el_cuelgue_de_octubre_ya_no_cuelga(self):
        r = subprocess.run([sys.executable, '-c', CUELGUE, RAIZ], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.stdout.split(), ['VIVO', 'LIBERADA'], r.stderr)


def app_falsa(**kw):
    app = types.SimpleNamespace(cfg=types.SimpleNamespace(dias_aviso=1, aprendido='', archivo=''),
                                sincro_retenidos=[], en_ui=lambda f: None, pausado=lambda: False,
                                pendientes=lambda: [], n_revision=lambda: 0, texto_estado=lambda: 'Todo bien')
    app.__dict__.update(kw)
    return app


class Icono(unittest.TestCase):
    def test_el_menu_nunca_espera_aunque_el_disco_se_atasque(self):
        atasco = threading.Event()
        app = app_falsa(pendientes=lambda: atasco.wait(30) and [])        # Descargas no contesta
        b = Bandeja(app)
        t0 = time.monotonic()
        b.actualizar()                                                   # desde cualquier hilo, sin esperar
        textos = [str(item.text) for item in b.icono.menu.items]
        self.assertLess(time.monotonic() - t0, 0.5)
        self.assertIn('Pendientes', textos)
        atasco.set()

    def test_cuenta_y_solo_rehace_el_menu_si_cambia(self):
        filas = [('a.pdf', 0, 10 * 86400), ('b.pdf', 0, 3600)]             # b se va mañana
        app = app_falsa(pendientes=lambda: filas, n_revision=lambda: 3, sincro_retenidos=[('x', ['H:'])])
        b = Bandeja(app)
        with mock.patch.object(b.icono, 'update_menu') as rehacer:
            b.refrescar()
            b.refrescar()
        self.assertEqual(rehacer.call_count, 1)
        self.assertEqual(b.estado['pendientes'], 'Pendientes (2)')
        self.assertEqual(b.estado['revision'], 'Revisión semanal (3)')
        self.assertEqual(b.estado['borrados'], 'Borrados por confirmar (1)')
        self.assertIn('1 a la Papelera mañana', b.icono.title)

    def test_avisos_largos_se_recortan(self):
        b = Bandeja(app_falsa())
        with mock.patch.object(b.icono, 'notify') as notify:
            b.notificar('T' * 100, 'x' * 1000)
        texto, titulo = notify.call_args[0]
        self.assertLessEqual(len(texto), 255)
        self.assertLessEqual(len(titulo), 63)


class SinEsperarCandados(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='hilos')
        self.cfg = Config(descargas=os.path.join(self.tmp, 'D'), onedrive=os.path.join(self.tmp, 'O'),
                          universidad='U', carpetas_indice=['U'], datos=self.tmp)
        os.makedirs(os.path.join(self.tmp, 'O', 'U'))
        for i in range(3):
            with open(os.path.join(self.tmp, 'O', 'U', f'{i}.txt'), 'w') as f:
                f.write(str(i))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ocupado(self, candado):
        """Otro hilo con el candado cogido (una pasada larga); devuelve cómo soltarlo."""
        cogido, soltar = threading.Event(), threading.Event()

        def hilo():
            with candado:
                cogido.set()
                soltar.wait(30)
        threading.Thread(target=hilo, daemon=True).start()
        cogido.wait(5)
        return soltar.set

    def test_progreso_del_indice_sin_candado(self):
        ind = Indice(self.cfg)
        self.assertEqual(ind.escanear(), (3, 0, 0))
        self.assertEqual(ind.progreso(), (0, 3))
        ind.trabajar(lambda: True, pausa=0)
        self.assertEqual(ind.progreso(), (3, 3))
        soltar = self.ocupado(ind._lock)
        t0 = time.monotonic()
        self.assertEqual(ind.progreso(), (3, 3))
        self.assertEqual(len(ind.filas_perfil()), 3)
        self.assertLess(time.monotonic() - t0, 0.5)
        soltar()
        ind.db.close()

    def test_los_word_no_esperan_a_la_pasada(self):
        w = Words(self.cfg)
        soltar = self.ocupado(w._lock)
        t0 = time.monotonic()
        self.assertEqual(w.filas(), [])
        self.assertLess(time.monotonic() - t0, 0.5)
        soltar()
        w.db.close()


class BucleInterfaz(unittest.TestCase):
    def app(self):
        cola = queue.Queue()
        root = mock.Mock()
        app = types.SimpleNamespace(_cola_ui=cola, root=root, _latido=0, _quizas_mostrar=mock.Mock(),
                                    _bucle_ui='siguiente vuelta')
        return app, cola, root

    def test_un_error_no_para_el_bucle(self):
        app, cola, root = self.app()
        hechos = []
        cola.put(lambda: 1 / 0)
        cola.put(lambda: hechos.append('después'))
        with self.assertLogs('organizador', 'ERROR'):
            A.App._bucle_ui(app)
        self.assertEqual(hechos, ['después'])
        root.after.assert_called_once()
        app._quizas_mostrar.assert_called_once()

    def test_sigue_aunque_falle_la_siguiente_descarga(self):
        app, cola, root = self.app()
        app._quizas_mostrar.side_effect = OSError('disco')
        with self.assertLogs('organizador', 'ERROR'):
            A.App._bucle_ui(app)
        root.after.assert_called_once()

    def test_el_error_de_un_trabajo_se_avisa(self):
        cola, avisos = [], []
        app = types.SimpleNamespace(en_ui=cola.append, bandeja=mock.Mock())
        app.bandeja.notificar = lambda t, x: avisos.append(x)
        hecho = threading.Event()

        def trabajo():
            try:
                raise FileNotFoundError('ya no está')
            finally:
                hecho.set()
        with self.assertLogs('organizador', 'ERROR'):
            A.App.ejecutar(app, trabajo, lambda r: cola.append(('fin', r)), 'mover «a.pdf»')
            hecho.wait(5)
            limite = time.monotonic() + 5
            while not cola and time.monotonic() < limite:
                time.sleep(0.02)
        self.assertEqual(avisos, ['No se pudo mover «a.pdf»: ya no está'])
        for f in list(cola):
            f()
        self.assertIn(('fin', None), cola)


if __name__ == '__main__':
    unittest.main()
