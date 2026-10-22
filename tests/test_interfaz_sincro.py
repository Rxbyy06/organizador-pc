"""La interfaz frente al sincronizador: ventana de borrados, decidir sin esperar y vigía de cuelgues.

    python -m unittest tests.test_interfaz_sincro
"""
import os
import shutil
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from organizador import app as A
from organizador import sincro as S
from organizador.config import Config
from organizador.ventanas_sincro import lineas_borrados

SEP = os.sep


class VentanaBorrados(unittest.TestCase):
    def test_lineas_agrupadas_por_carpeta(self):
        ret = [(f'U{SEP}repo{SEP}datos{SEP}{i}.txt', ['G:', 'H:']) for i in range(3000)] + \
              [(f'U{SEP}suelto.pdf', ['H:'])]
        self.assertEqual(lineas_borrados(ret), [f'U{SEP}suelto.pdf  ·  falta en H:',
                                                f'U{SEP}repo{SEP}datos{SEP}  ·  3000 archivos  ·  falta en G:, H:'])


class Decidir(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='interfaz')
        cfg = Config(descargas=os.path.join(self.tmp, 'D'), onedrive=os.path.join(self.tmp, 'O'),
                     universidad='1 - Uni', carpetas_indice=['1 - Uni'], datos=self.tmp, copias=[])
        self.s = S.Sincronizador(cfg)

    def tearDown(self):
        self.s.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_la_interfaz_no_espera_a_la_pasada(self):
        ret = [(os.path.join('1 - Uni', f'{i}.txt'), ['H:']) for i in range(6633)]
        cola = []
        app = types.SimpleNamespace(sincro=self.s, sincro_retenidos=list(ret), bandeja=mock.Mock(),
                                    en_ui=cola.append, sincronizar_ahora=mock.Mock())
        app.ejecutar = lambda *a, **kw: A.App.ejecutar(app, *a, **kw)
        with self.s._lock:                                   # una pasada en marcha
            t0 = time.monotonic()
            A.App.decidir_borrados(app, ret, 'borrar')
            self.assertLess(time.monotonic() - t0, 1)
        self.assertEqual(app.sincro_retenidos, [])           # la bandeja deja de ofrecerlos en el acto
        limite = time.monotonic() + 10
        while len(cola) < 2 and time.monotonic() < limite:   # el guardado (en otro hilo) vuelve a la interfaz
            time.sleep(0.05)
        for f in cola:
            f()
        app.sincronizar_ahora.assert_called_once()
        self.assertEqual(set(self.s.decisiones()), {S.clave(r) for r, _ in ret})


class Vigia(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='vigia')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def vigilar(self, latido):
        app = types.SimpleNamespace(cfg=types.SimpleNamespace(datos=self.tmp), _parar=threading.Event(),
                                    _latido=latido)
        with mock.patch.object(A, 'VIGIA_CADA', 0.05):
            t = threading.Thread(target=A.App._hilo_vigia, args=(app,))
            t.start()
            time.sleep(0.5)
            app._parar.set()
            t.join(5)
        with open(os.path.join(self.tmp, 'cuelgues.log'), encoding='utf-8', errors='replace') as f:
            return f.read()

    def test_interfaz_parada_apunta_cada_hilo_una_vez(self):
        with self.assertLogs('organizador', 'WARNING'):
            texto = self.vigilar(time.monotonic() - 100)
        self.assertEqual(texto.count('sin responder'), 1)      # una vez por cuelgue, no en cada vuelta
        self.assertIn('_hilo_vigia', texto)                     # la pila de los hilos

    def test_interfaz_viva_no_apunta_nada(self):
        self.assertEqual(self.vigilar(time.monotonic()), '')


if __name__ == '__main__':
    unittest.main()
