"""Aviso de espacio, resumen semanal (duplicados y números) y copia semanal.
python -m unittest tests.test_resumen_espacio_copia"""
import datetime
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
import zipfile
from collections import namedtuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from organizador import copia, espacio, papelera
from organizador.acciones import Historial
from organizador.config import Config
from organizador.huellas import Indice
from organizador.resumen import Resumen
from organizador.revision import Revision

Disco = namedtuple('Disco', 'total used free')
GB = 1 << 30


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='f5')
        self.O = os.path.join(self.tmp, 'O')
        self.cfg = Config(descargas=os.path.join(self.tmp, 'D'), onedrive=self.O, universidad='1 - Uni',
                          carpetas_indice=['1 - Uni'], datos=os.path.join(self.tmp, 'datos'),
                          copias=[{'nombre': 'H:', 'raiz': os.path.join(self.tmp, 'H'), 'carpetas': ['1 - Uni']}],
                          carpeta_copia=os.path.join(self.tmp, 'O', '9 - Personal', 'Copia del Organizador'),
                          copias_guardar=2, aprendido=os.path.join(self.tmp, 'aprendido.txt'),
                          archivo=os.path.join(self.tmp, 'config.toml'))
        os.makedirs(self.cfg.datos)
        self.h = Historial(self.cfg)
        self.papeleras = []

    def tearDown(self):
        for ruta, fecha in self.papeleras:
            try:
                papelera.restaurar(ruta, fecha)
            except OSError:
                pass
        self.h.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def escribir(self, rel, texto):
        p = os.path.join(self.O, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w', encoding='utf-8') as f:
            f.write(texto)
        return p


class Espacio(Base):
    def test_umbrales(self):
        os.makedirs(self.O)
        disco =lambda ruta: Disco(15 * GB, int(14.6 * GB), int(0.4 * GB))       # H: como ahora
        usos = espacio.medir(self.cfg, disco=disco, tamano=lambda r: int(3.06 * GB))
        o, h = usos
        self.assertEqual((o.sitio, round(o.pct), o.aviso), ('OneDrive', 61, False))
        self.assertEqual((h.sitio, h.aviso), ('H:', True))
        self.assertIn('97 % lleno', h.texto())
        usos = espacio.medir(self.cfg, disco=lambda r: Disco(15 * GB, 10 * GB, 5 * GB), tamano=lambda r: int(4.6 * GB))
        self.assertEqual([u.aviso for u in usos], [True, False])                 # OneDrive al 92 %


class Resumenes(Base):
    def indice_con(self, archivos):
        ind = Indice(self.cfg)
        for rel, texto in archivos:
            self.escribir(rel, texto)
        ind.escanear()
        ind.trabajar(lambda: True, pausa=0)
        ind.db.close()

    def test_duplicados_sin_repos_y_solo_los_nuevos(self):
        os.makedirs(os.path.join(self.O, '1 - Uni', 'P1', '.git'))
        self.indice_con([('1 - Uni/a/tema.pdf', 'igual'), ('1 - Uni/b/tema (copia).pdf', 'igual'),
                         ('1 - Uni/P1/datos.txt', 'repo'), ('1 - Uni/P1/otra/datos.txt', 'repo'),
                         ('1 - Uni/c/único.pdf', 'único')])
        r = Resumen(self.cfg, self.h)
        grupos = r.duplicados()
        self.assertEqual(len(grupos), 1)                                      # los del repo no cuentan
        self.assertEqual(sorted(os.path.basename(x) for x in grupos[0].rutas), ['tema (copia).pdf', 'tema.pdf'])
        d = r.datos([], 0, [])
        r.hecho(d)
        self.assertEqual(r.duplicados(), [])                                  # ya enseñado: no vuelve como nuevo
        self.assertEqual(len(r.duplicados(solo_nuevos=False)), 1)
        r.ignorar(grupos[0])
        self.assertEqual(r.duplicados(solo_nuevos=False), [])                 # «No volver a avisar»

    def test_numeros_de_la_semana_y_si_merece_ventana(self):
        self.indice_con([('1 - Uni/x.pdf', 'x')])
        ahora = time.time()
        self.h.apuntar('sincro', {'copiados': {'H:': 3}, 'movidos': {'G:': 1}, 'a_papelera': 2, 'conflictos': [],
                                  'errores': []}, ahora - 3600)
        self.h.apuntar('sincro', {'copiados': {'H:': 2}, 'movidos': {}, 'a_papelera': 0, 'conflictos': [],
                                  'errores': []}, ahora - 60)
        self.h.registrar('mover', 'Movido «a.pdf»', [], 'hecho')
        r = Resumen(self.cfg, self.h)
        d = r.datos([], 0, [])
        self.assertEqual((d.pasadas, d.copiados['H:'], d.movidos['G:'], d.a_papelera, d.acciones['mover']),
                         (2, 5, 1, 2, 1))
        self.assertFalse(d.notable)                                           # semana normal: solo notificación
        self.h.apuntar('sincro', {'copiados': {}, 'movidos': {}, 'a_papelera': 0,
                                  'conflictos': ['1 - Uni\\x (conflicto 2026-10-21).pdf'], 'errores': []})
        self.assertTrue(r.datos([], 0, []).notable)                           # un conflicto: ventana


class CopiaSemanal(Base):
    def test_copia_con_datos_y_solo_las_ultimas(self):
        with open(self.cfg.aprendido, 'w', encoding='utf-8') as f:
            f.write('curso 1 = X\n')
        with open(self.cfg.archivo, 'w', encoding='utf-8') as f:
            f.write('[rutas]\n')
        self.h.registrar('mover', 'algo', [], 'hecho')
        hoy = datetime.date(2026, 10, 26)
        rutas = []
        for semana in range(3):
            t0 = time.time()
            ruta, quitadas = copia.hacer_copia(self.cfg, hoy + datetime.timedelta(days=7 * semana))
            self.papeleras += [(q, t0) for q in quitadas]
            rutas.append(ruta)
        with zipfile.ZipFile(rutas[-1]) as z:
            nombres = set(z.namelist())
            self.assertTrue({'aprendido.txt', 'config.toml', 'datos/historial.sqlite'} <= nombres)
            z.extract('datos/historial.sqlite', self.tmp)
        n = sqlite3.connect(os.path.join(self.tmp, 'datos', 'historial.sqlite')).execute(
            'SELECT count(*) FROM acciones').fetchone()[0]
        self.assertEqual(n, 1)                                                # la base copiada se puede abrir
        quedan = sorted(os.listdir(self.cfg.carpeta_copia))
        self.assertEqual(quedan, ['Organizador 2026-11-02.zip', 'Organizador 2026-11-09.zip'])   # guardar = 2


class TurnoSemanal(Base):
    def test_turno_aunque_no_haya_capturas(self):
        lunes = datetime.datetime(2026, 10, 26, 9).timestamp()
        r = Revision(self.cfg, self.h, lambda: lunes)
        self.assertTrue(r.turno_pendiente())
        r.hecha()
        self.assertFalse(r.turno_pendiente())


if __name__ == '__main__':
    unittest.main()
