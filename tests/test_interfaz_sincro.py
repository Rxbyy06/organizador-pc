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
from organizador.ventanas_sincro import grupos_borrados

SEP = os.sep


class VentanaBorrados(unittest.TestCase):
    def test_agrupados_por_carpeta_sin_perder_ningun_nombre(self):
        ret = [(f'U{SEP}repo{SEP}datos{SEP}{i}.txt', ['G:', 'H:']) for i in range(3000)] + \
              [(f'U{SEP}suelto.pdf', ['H:'])]
        grupos = grupos_borrados(ret)
        self.assertEqual([c for c, _ in grupos], ['U', f'U{SEP}repo{SEP}datos'])
        self.assertEqual(grupos[0][1], [('suelto.pdf', ['H:'])])
        self.assertEqual(len(grupos[1][1]), 3000)                     # cada archivo, con su nombre
        self.assertEqual(grupos[1][1][0], ('0.txt', ['G:', 'H:']))


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

    def vigilar(self, latido, muertos=(), reinicios=0, segundos=0.5, **cambios):
        cola = []
        self.app = types.SimpleNamespace(cfg=types.SimpleNamespace(datos=self.tmp), _parar=threading.Event(),
                                         _latido=latido, reinicios=reinicios, _hilos_parados=lambda: list(muertos),
                                         _reiniciar=mock.Mock(), en_ui=cola.append, _revisar_descargas='repaso')
        self.cola = cola
        with mock.patch.multiple(A, VIGIA_CADA=0.05, **cambios):
            t = threading.Thread(target=A.App._hilo_vigia, args=(self.app,))
            t.start()
            time.sleep(segundos)
            self.app._parar.set()
            t.join(5)
        self.assertFalse(t.is_alive())
        with open(os.path.join(self.tmp, 'cuelgues.log'), encoding='utf-8', errors='replace') as f:
            return f.read()

    def test_interfaz_parada_apunta_cada_hilo_una_vez(self):
        with self.assertLogs('organizador', 'WARNING'):
            texto = self.vigilar(time.monotonic() - 100)
        self.assertEqual(texto.count('sin responder'), 1)      # una vez por cuelgue, no en cada vuelta
        self.assertIn('_hilo_vigia', texto)                     # la pila de los hilos
        self.app._reiniciar.assert_not_called()                 # 100 s: aún no toca reiniciar

    def test_interfaz_viva_no_apunta_nada(self):
        self.assertEqual(self.vigilar(time.monotonic()), '')
        self.app._reiniciar.assert_not_called()

    def test_cuelgue_largo_reinicia(self):
        with self.assertLogs('organizador', 'WARNING'):
            texto = self.vigilar(time.monotonic() - A.SEGUNDOS_REINICIO - 5)
        self.app._reiniciar.assert_called()
        self.assertIn('lleva', self.app._reiniciar.call_args[0][0])
        self.assertIn('reinicio automático', texto)

    def test_hilo_parado_reinicia(self):
        self.vigilar(time.monotonic(), muertos=['sincro'])
        self.app._reiniciar.assert_called()
        self.assertIn('sincro', self.app._reiniciar.call_args[0][0])

    def test_no_reinicia_en_bucle(self):
        with self.assertLogs('organizador', 'ERROR') as registro:
            self.vigilar(time.monotonic(), muertos=['sincro'], reinicios=A.MAX_REINICIOS)
        self.app._reiniciar.assert_not_called()
        self.assertEqual(sum('no lo vuelvo a hacer' in r for r in registro.output), 1)   # se dice una vez

    def test_suspension_no_es_cuelgue(self):
        reloj = iter([0.0] + [1000.0 + i for i in range(1000)])      # el reloj salta 1000 s: el PC dormía
        with mock.patch.object(A.time, 'time', lambda: next(reloj)):
            texto = self.vigilar(time.monotonic() - 500)
        self.assertNotIn('sin responder', texto)
        self.app._reiniciar.assert_not_called()

    def test_repasa_descargas(self):
        self.vigilar(time.monotonic(), REPASO_DESCARGAS=0.1)
        self.assertIn('repaso', self.cola)


if __name__ == '__main__':
    unittest.main()
