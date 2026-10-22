"""Limpieza de Descargas y revisión semanal, con un reloj simulado.  python -m unittest tests.test_limpieza_revision

Usa carpetas temporales; lo que va a la Papelera se recupera con «Deshacer» al final de cada prueba.
"""
import datetime
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from organizador.acciones import Ejecutor, Historial
from organizador.config import Config
from organizador.limpieza import Limpieza
from organizador.revision import Revision, fecha_de, nombre_sugerido

DIA = 86400
LUNES = datetime.datetime(2026, 10, 19, 10, 0).timestamp()      # lunes 19-10-2026, 10:00


class Reloj:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t

    def pasar(self, dias):
        self.t += dias * DIA


class _Indice:            # el ejecutor avisa al índice de lo que mueve; aquí no hace falta
    def quitar(self, *a):
        pass

    def anadir(self, *a):
        pass


def entorno(d):
    os.makedirs(os.path.join(d, 'Downloads'))
    os.makedirs(os.path.join(d, 'Capturas'))
    cfg = Config(descargas=os.path.join(d, 'Downloads'), onedrive=os.path.join(d, 'OneDrive'), universidad='U',
                 simulacion=False, ignorar=['desktop.ini'], datos=os.path.join(d, 'datos'),
                 carpetas_capturas=[os.path.join(d, 'Capturas')])
    os.makedirs(cfg.datos)
    h = Historial(cfg)
    return cfg, h, Ejecutor(cfg, h, _Indice(), None)


def crear(ruta, texto='x'):
    with open(ruta, 'w') as f:
        f.write(texto)
    return ruta


class LimpiezaDescargas(unittest.TestCase):
    def test_avisa_el_dia_6_y_tira_el_7(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            cfg, h, ej = entorno(d)
            reloj = Reloj(LUNES)
            lim = Limpieza(cfg, h, ej, reloj)
            a = crear(os.path.join(cfg.descargas, 'factura.pdf'))
            os.makedirs(os.path.join(cfg.descargas, 'carpeta suelta'))
            h.descarga_nueva('factura.pdf', cuando=reloj())
            self.assertEqual(lim.revisar(), ([], []))           # la carpeta empieza a contar hoy
            reloj.pasar(5)
            self.assertEqual(lim.revisar(), ([], []))
            reloj.pasar(1)                                        # día 6: aviso
            avisados, tirados = lim.revisar()
            self.assertEqual([os.path.basename(r) for r in sorted(avisados)], ['carpeta suelta', 'factura.pdf'])
            self.assertEqual(tirados, [])
            self.assertEqual(lim.revisar(), ([], []))             # el aviso no se repite
            reloj.pasar(1)                                        # día 7: a la Papelera
            avisados, tirados = lim.revisar()
            self.assertEqual(len(tirados), 2)
            self.assertFalse(os.path.exists(a))
            # Deshacer: todo vuelve a Descargas
            id_ = h.lista()[0][0]
            ej.deshacer(id_)
            self.assertTrue(os.path.exists(a) and os.path.isdir(os.path.join(cfg.descargas, 'carpeta suelta')))

    def test_pc_apagado_10_dias_primero_avisa(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            cfg, h, ej = entorno(d)
            reloj = Reloj(LUNES)
            lim = Limpieza(cfg, h, ej, reloj)
            a = crear(os.path.join(cfg.descargas, 'instalador.exe'))
            h.descarga_nueva('instalador.exe', cuando=reloj())
            reloj.pasar(10)                                       # nadie lo vio en 10 días
            avisados, tirados = lim.revisar()
            self.assertEqual((len(avisados), tirados), (1, []))   # primero, el aviso
            reloj.t += 12 * 3600
            self.assertEqual(lim.revisar(), ([], []))             # medio día después, aún no
            reloj.t += 12 * 3600
            self.assertEqual(len(lim.revisar()[1]), 1)            # al día siguiente, sí
            ej.deshacer(h.lista()[0][0])
            self.assertTrue(os.path.exists(a))

    def test_lo_que_se_organiza_no_se_tira(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            cfg, h, ej = entorno(d)
            reloj = Reloj(LUNES)
            lim = Limpieza(cfg, h, ej, reloj)
            a = crear(os.path.join(cfg.descargas, 'apuntes.pdf'))
            h.descarga_nueva('apuntes.pdf', cuando=reloj())
            reloj.pasar(6)
            lim.revisar()
            os.remove(a)                                          # lo movió a su carpeta
            reloj.pasar(1)
            self.assertEqual(lim.revisar(), ([], []))
            self.assertIsNone(h.descarga_info('apuntes.pdf'))


class RevisionSemanal(unittest.TestCase):
    def test_toca_los_lunes_y_si_el_pc_estaba_apagado(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            cfg, h, ej = entorno(d)
            reloj = Reloj(LUNES)
            rev = Revision(cfg, h, reloj)
            crear(os.path.join(cfg.carpetas_capturas[0], 'Captura de pantalla 2026-10-01 101010.png'))
            self.assertTrue(rev.toca())
            rev.hecha()
            self.assertFalse(rev.toca())
            reloj.pasar(3)                                        # jueves
            self.assertFalse(rev.toca())
            reloj.pasar(5)                                        # el martes siguiente (el lunes, apagado)
            self.assertTrue(rev.toca())
            rev.posponer()                                        # «Más tarde»
            self.assertFalse(rev.toca())
            reloj.pasar(1)
            self.assertTrue(rev.toca())

    def test_solo_las_de_mas_de_7_dias_y_sin_nada_no_molesta(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            cfg, h, ej = entorno(d)
            reloj = Reloj(LUNES)
            rev = Revision(cfg, h, reloj)
            crear(os.path.join(cfg.carpetas_capturas[0], 'Captura de pantalla 2026-10-15 101010.png'))   # 4 días
            crear(os.path.join(cfg.carpetas_capturas[0], 'notas.txt'))
            self.assertEqual(rev.pendientes(), [])
            self.assertFalse(rev.toca())                          # nada que revisar: no se abre
            vieja = crear(os.path.join(cfg.carpetas_capturas[0], 'Captura de pantalla 2026-10-05 090000.png'))
            self.assertEqual(rev.pendientes(), [vieja])

    def test_dejar_sigue_saliendo_un_mes_y_luego_se_queda(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            cfg, h, ej = entorno(d)
            reloj = Reloj(LUNES)
            rev = Revision(cfg, h, reloj)
            c = crear(os.path.join(cfg.carpetas_capturas[0], 'Captura de pantalla 2026-10-01 101010.png'))
            rev.dejar(c)
            for semana in range(1, 4):
                reloj.pasar(7)
                self.assertEqual(rev.pendientes(), [c], f'semana {semana}')
                rev.dejar(c)                                      # la vuelve a dejar: cuenta desde la primera vez
            reloj.pasar(7)                                        # 4 semanas: ya no sale nunca más
            self.assertEqual(rev.pendientes(), [])

    def test_aplicar_borra_guarda_y_se_deshace(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            cfg, h, ej = entorno(d)
            cap = cfg.carpetas_capturas[0]
            b = crear(os.path.join(cap, 'Captura de pantalla 2026-10-01 101010.png'))
            g = crear(os.path.join(cap, 'Captura de pantalla 2026-10-02 111111.png'))
            destino = os.path.join(cfg.onedrive, '9 - Personal y hogar', 'Capturas guardadas')
            ej.revisar_capturas([b], [(g, destino, 'Captura 2026-10-02.png')])
            self.assertFalse(os.path.exists(b) or os.path.exists(g))
            self.assertTrue(os.path.exists(os.path.join(destino, 'Captura 2026-10-02.png')))
            ej.deshacer(h.lista()[0][0])
            self.assertTrue(os.path.exists(b) and os.path.exists(g))
            self.assertFalse(os.path.exists(destino))             # la carpeta creada se quita al deshacer

    def test_nombre_y_fecha(self):
        r = r'C:\x\Captura de pantalla 2026-10-21 121613.png'
        self.assertEqual(datetime.datetime.fromtimestamp(fecha_de(r)), datetime.datetime(2026, 10, 21, 12, 16, 13))
        self.assertEqual(nombre_sugerido(r), 'Captura 2026-10-21.png')


if __name__ == '__main__':
    unittest.main()
