"""Sincronizador con tres carpetas locales que hacen de OneDrive, G: y H:.  python -m unittest tests.test_sincro

Todo lo que va a la papelera durante las pruebas se recupera al final de cada una (y luego se borra la carpeta
temporal), para no dejar nada en la Papelera de verdad.
"""
import os
import shutil
import sys
import tempfile
import threading
import time
import unicodedata
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from organizador import papelera
from organizador import sincro as S
from organizador.config import Config

UNI, OTRA = '1 - Uni', '2 - Otra'
VIEJO = time.time() - 3 * 86400


def escribir(ruta, texto, mtime=None):
    os.makedirs(os.path.dirname(S.ruta_larga(ruta)), exist_ok=True)
    with open(S.ruta_larga(ruta), 'w', encoding='utf-8') as f:
        f.write(texto)
    t = mtime or time.time()
    os.utime(S.ruta_larga(ruta), (t, t))


def leer(ruta):
    with open(S.ruta_larga(ruta), encoding='utf-8') as f:
        return f.read()


def arbol(raiz):
    res = {}
    for r, ds, fs in os.walk(S.ruta_larga(raiz)):
        for f in fs:
            p = os.path.join(r, f)
            res[unicodedata.normalize('NFC', os.path.relpath(p, S.ruta_larga(raiz)))] = leer(p)
    return res


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='sinc')
        self.O, self.G, self.H = (os.path.join(self.tmp, x) for x in 'OGH')
        self.cfg = Config(descargas=os.path.join(self.tmp, 'D'), onedrive=self.O, universidad=UNI,
                          carpetas_indice=[UNI, OTRA], datos=os.path.join(self.tmp, 'datos'),
                          sincro_simulacion=False, max_borrados=3, minutos_repo=10,
                          copias=[{'nombre': 'G:', 'raiz': self.G, 'carpetas': [UNI]},
                                  {'nombre': 'H:', 'raiz': self.H, 'carpetas': [UNI, OTRA]}])
        os.makedirs(self.cfg.datos)
        # Los tres sitios, iguales: 6 archivos en la uni y 2 en la otra carpeta (G: solo tiene la uni).
        for raiz, carpetas in ((self.O, [UNI, OTRA]), (self.G, [UNI]), (self.H, [UNI, OTRA])):
            for c in carpetas:
                os.makedirs(os.path.join(raiz, c))
            for i in range(6):
                escribir(os.path.join(raiz, UNI, 'Mates', f'Tema {i}.pdf'), f'tema {i}', VIEJO)
            if OTRA in carpetas:
                escribir(os.path.join(raiz, OTRA, 'nota.txt'), 'nota', VIEJO)
                escribir(os.path.join(raiz, OTRA, 'sub', 'foto.jpg'), 'foto', VIEJO)
        self.s = S.Sincronizador(self.cfg)
        ok, msg = self.s.crear_estado_inicial()
        self.assertTrue(ok, msg)
        self.papeleras = []

    def tearDown(self):
        for paso in self.papeleras:                   # devolver de la Papelera lo que mandaron las pruebas
            try:
                papelera.restaurar(paso['ruta'], paso['fecha'])
            except OSError:
                pass
        self.s.db.close()
        shutil.rmtree('\\\\?\\' + self.tmp, ignore_errors=True)

    def pasada(self, **kw):
        inf = self.s.pasada(**kw)
        self.papeleras += inf.pasos
        return inf

    def iguales(self):
        o, g, h = arbol(self.O), arbol(self.G), arbol(self.H)
        self.assertEqual(h, o)
        self.assertEqual(g, {k: v for k, v in o.items() if k.startswith(UNI)})
        self.assertEqual(self.pasada().resumen(), 'todo igual')        # y la siguiente pasada no hace nada
        return o


class Casos(Base):
    def test_inicial_sin_cambios(self):
        self.assertEqual(self.pasada().resumen(), 'todo igual')

    def test_nuevo_en_onedrive_va_a_g_y_h_segun_carpeta(self):
        escribir(os.path.join(self.O, UNI, 'Mates', 'Examen.pdf'), 'examen')
        escribir(os.path.join(self.O, OTRA, 'carta.txt'), 'carta')
        inf = self.pasada()
        self.assertEqual((inf.copiados['G:'], inf.copiados['H:']), (1, 2))
        o = self.iguales()
        self.assertNotIn(os.path.join(OTRA, 'carta.txt'), arbol(self.G))
        self.assertIn(os.path.join(OTRA, 'carta.txt'), o)

    def test_cambio_en_h_llega_a_onedrive_y_g(self):
        escribir(os.path.join(self.H, UNI, 'Mates', 'Tema 1.pdf'), 'tema 1 corregido')
        inf = self.pasada()
        self.assertEqual((inf.copiados['OneDrive'], inf.copiados['G:']), (1, 1))
        self.assertEqual(leer(os.path.join(self.G, UNI, 'Mates', 'Tema 1.pdf')), 'tema 1 corregido')
        self.iguales()

    def test_renombrado_en_g_se_mueve_no_se_copia(self):
        os.rename(os.path.join(self.G, UNI, 'Mates', 'Tema 2.pdf'), os.path.join(self.G, UNI, 'Mates', 'Tema 02 - Límites.pdf'))
        inf = self.pasada()
        self.assertEqual((inf.movidos['OneDrive'], inf.movidos['H:'], sum(inf.copiados.values()), inf.a_papelera),
                         (1, 1, 0, []))
        self.assertIn(os.path.join(UNI, 'Mates', 'Tema 02 - Límites.pdf'), self.iguales())

    def test_carpeta_renombrada_es_una_sola_operacion(self):
        os.rename(os.path.join(self.O, UNI, 'Mates'), os.path.join(self.O, UNI, 'Matemàtiques'))
        inf = self.pasada()
        self.assertEqual((inf.movidos['G:'], inf.movidos['H:'], sum(inf.copiados.values()), inf.a_papelera),
                         (1, 1, 0, []))
        self.assertFalse(os.path.exists(os.path.join(self.H, UNI, 'Mates')))
        self.iguales()

    def test_carpeta_renombrada_con_un_archivo_cambiado_sigue_siendo_una_operacion(self):
        """Como un repo renombrado cuyo .git\\index cambió después: antes eran miles de movimientos sueltos."""
        os.rename(os.path.join(self.O, UNI, 'Mates'), os.path.join(self.O, UNI, 'Matemàtiques'))
        escribir(os.path.join(self.O, UNI, 'Matemàtiques', 'Tema 1.pdf'), 'tema 1 nuevo')
        inf = self.pasada()
        self.assertEqual((inf.movidos['G:'], inf.movidos['H:'], inf.copiados['G:'], inf.copiados['H:']), (1, 1, 1, 1))
        viejo = os.path.join(UNI, 'Mates', 'Tema 1.pdf')
        self.assertEqual(sorted(inf.a_papelera), [f'G:: {viejo}', f'H:: {viejo}'])   # desde su sitio de antes
        self.assertFalse(os.path.exists(os.path.join(self.G, UNI, 'Mates')))
        self.assertEqual(self.iguales()[os.path.join(UNI, 'Matemàtiques', 'Tema 1.pdf')], 'tema 1 nuevo')

    def test_carpeta_metida_en_otra_es_una_sola_operacion(self):
        escribir(os.path.join(self.O, OTRA, 'sub', 'foto 2.jpg'), 'foto 2', VIEJO)
        self.pasada()
        os.makedirs(os.path.join(self.O, OTRA, 'Fotos'))
        os.rename(os.path.join(self.O, OTRA, 'sub'), os.path.join(self.O, OTRA, 'Fotos', 'sub'))
        inf = self.pasada()
        self.assertEqual((inf.movidos['H:'], sum(inf.copiados.values()), inf.a_papelera), (1, 0, []))
        self.assertTrue(any('renombrar carpeta' in p for p in inf.plan))
        self.iguales()

    def test_destino_con_carpetas_vacias(self):
        """Una pasada anterior ya creó la carpeta nueva (vacía) en G:: se quita y se renombra la vieja."""
        os.makedirs(os.path.join(self.G, UNI, 'Matemàtiques', 'Apuntes'))
        os.rename(os.path.join(self.O, UNI, 'Mates'), os.path.join(self.O, UNI, 'Matemàtiques'))
        inf = self.pasada()
        self.assertEqual((inf.movidos['G:'], inf.movidos['H:'], sum(inf.copiados.values()), inf.a_papelera),
                         (1, 1, 0, []))
        for raiz in (self.O, self.G, self.H):                      # la subcarpeta vacía se conserva en todos
            self.assertTrue(os.path.isdir(os.path.join(raiz, UNI, 'Matemàtiques', 'Apuntes')))
        self.iguales()

    def test_simulacion_de_carpeta_renombrada(self):
        os.rename(os.path.join(self.O, UNI, 'Mates'), os.path.join(self.O, UNI, 'Matemàtiques'))
        inf = self.pasada(simulacion=True)
        self.assertEqual(sorted(p.split(' «')[0] for p in inf.plan), ['[G:] renombrar carpeta', '[H:] renombrar carpeta'])
        self.assertTrue(os.path.exists(os.path.join(self.G, UNI, 'Mates', 'Tema 1.pdf')))

    def test_borrado_en_h_va_a_la_papelera_en_los_demas(self):
        os.remove(os.path.join(self.H, UNI, 'Mates', 'Tema 3.pdf'))
        inf = self.pasada()
        self.assertEqual(len(inf.a_papelera), 2)
        self.assertEqual(len(inf.pasos), 2)
        self.assertTrue(all(papelera.buscar(p['ruta']) for p in inf.pasos))   # de verdad en la papelera
        self.iguales()

    def test_conflicto_guarda_las_dos_versiones(self):
        escribir(os.path.join(self.O, UNI, 'Mates', 'Tema 4.pdf'), 'versión OneDrive', time.time() - 60)
        escribir(os.path.join(self.H, UNI, 'Mates', 'Tema 4.pdf'), 'versión H, más nueva', time.time())
        inf = self.pasada()
        self.assertEqual(len(inf.conflictos), 1)
        o = self.iguales()
        self.assertEqual(o[os.path.join(UNI, 'Mates', 'Tema 4.pdf')], 'versión H, más nueva')
        conflicto = [k for k in o if 'conflicto' in k]
        self.assertEqual(len(conflicto), 1)
        self.assertEqual(o[conflicto[0]], 'versión OneDrive')
        self.assertRegex(conflicto[0], r'Tema 4 \(conflicto \d{4}-\d\d-\d\d\)\.pdf$')

    def test_modificar_gana_a_borrar(self):
        escribir(os.path.join(self.O, UNI, 'Mates', 'Tema 0.pdf'), 'tema 0 nuevo')
        os.remove(os.path.join(self.G, UNI, 'Mates', 'Tema 0.pdf'))
        self.pasada()
        self.assertEqual(leer(os.path.join(self.G, UNI, 'Mates', 'Tema 0.pdf')), 'tema 0 nuevo')
        self.iguales()

    def test_mover_fuera_de_la_uni(self):
        shutil.move(os.path.join(self.O, UNI, 'Mates', 'Tema 5.pdf'), os.path.join(self.O, OTRA, 'Tema 5.pdf'))
        inf = self.pasada()
        self.assertEqual((inf.movidos['H:'], len(inf.a_papelera), sum(inf.copiados.values())), (1, 1, 0))
        self.iguales()

    def test_borrar_carpeta_con_pocos_archivos(self):
        shutil.rmtree(os.path.join(self.O, OTRA, 'sub'))
        inf = self.pasada()
        self.assertEqual(len(inf.a_papelera), 1)
        self.assertFalse(os.path.exists(os.path.join(self.H, OTRA, 'sub')))   # la carpeta vacía también se va
        self.iguales()

    def test_conflicto_entre_g_y_h(self):
        escribir(os.path.join(self.G, UNI, 'Mates', 'Tema 1.pdf'), 'desde G', time.time() - 30)
        escribir(os.path.join(self.H, UNI, 'Mates', 'Tema 1.pdf'), 'desde H', time.time())
        inf = self.pasada()
        self.assertEqual(len(inf.conflictos), 1)
        o = self.iguales()
        self.assertEqual(o[os.path.join(UNI, 'Mates', 'Tema 1.pdf')], 'desde H')
        self.assertIn('desde G', o.values())

    def test_nfd_y_rutas_largas(self):
        nfd = unicodedata.normalize('NFD', 'Pràctica àèíóú.txt')
        escribir(os.path.join(self.H, UNI, nfd), 'nfd')
        larga = os.path.join(self.O, UNI, *(['Carpeta con un nombre bastante largo'] * 7), 'archivo final.txt')
        self.assertGreater(len(larga), 260)
        escribir(larga, 'larga')
        self.pasada()
        self.iguales()


class Seguridad(Base):
    def test_freno_de_borrados_y_recuperar(self):
        for i in range(5):                                         # max_borrados = 3 en estas pruebas
            os.remove(os.path.join(self.H, UNI, 'Mates', f'Tema {i}.pdf'))
        inf = self.pasada()
        self.assertEqual((len(inf.retenidos), inf.a_papelera), (5, []))
        self.assertEqual(len(arbol(self.O)), 8)                     # en OneDrive no se ha tocado nada
        self.assertEqual(len(self.pasada().retenidos), 5)           # sigue esperando
        self.s.decidir([S.clave(os.path.join(UNI, 'Mates', f'Tema {i}.pdf')) for i in range(5)], 'recuperar')
        inf = self.pasada()
        self.assertEqual(inf.copiados['H:'], 5)
        self.iguales()

    def test_freno_de_borrados_y_confirmar(self):
        for i in range(5):
            os.remove(os.path.join(self.H, UNI, 'Mates', f'Tema {i}.pdf'))
        inf = self.pasada()
        self.s.decidir([S.clave(os.path.join(UNI, 'Mates', f'Tema {i}.pdf')) for i in range(5)], 'borrar')
        inf = self.pasada()
        self.assertEqual(len(inf.a_papelera), 10)                   # 5 en OneDrive y 5 en G:
        self.iguales()

    def test_unidad_desconectada_no_es_borrarlo_todo(self):
        os.rename(self.H, self.H + '_fuera')
        escribir(os.path.join(self.O, UNI, 'nuevo.pdf'), 'nuevo')
        inf = self.pasada()
        self.assertIn('H:', inf.no_disponibles)
        self.assertEqual(inf.a_papelera, [])
        os.rename(self.H + '_fuera', self.H)
        self.pasada()                                               # al volver, recibe lo que se perdió
        self.iguales()

    def test_falta_una_carpeta_principal_entera(self):
        shutil.move(os.path.join(self.H, OTRA), os.path.join(self.tmp, 'apartada'))
        inf = self.pasada()
        self.assertIn('H:', inf.no_disponibles)
        self.assertEqual(inf.a_papelera, [])
        self.assertTrue(any('falta la carpeta' in a for a in inf.avisos))

    def test_h_sin_espacio(self):
        escribir(os.path.join(self.O, OTRA, 'grande.bin'), 'x' * 1000)
        real = shutil.disk_usage

        def falso(ruta):
            if os.path.normcase(str(ruta)).startswith(os.path.normcase(self.H)):
                return type(real(self.tmp))(100, 100, S.MARGEN_ESPACIO + 10)
            return real(ruta)
        with mock.patch.object(S.shutil, 'disk_usage', falso):
            inf = self.pasada()
        self.assertEqual(inf.sin_espacio['H:'], 1)
        self.assertFalse(os.path.exists(os.path.join(self.H, OTRA, 'grande.bin')))
        self.pasada()                                               # con espacio, se copia en la siguiente
        self.iguales()

    def test_archivo_abierto_se_reintenta(self):
        import win32file
        ruta = os.path.join(self.O, UNI, 'Mates', 'Tema 5.pdf')
        escribir(ruta, 'tema 5 nuevo')
        h = win32file.CreateFile(ruta, win32file.GENERIC_READ, 0, None, win32file.OPEN_EXISTING, 0, None)
        try:
            inf = self.pasada()
            self.assertTrue(inf.errores)
            self.assertEqual(leer(os.path.join(self.H, UNI, 'Mates', 'Tema 5.pdf')), 'tema 5')
        finally:
            h.Close()
        self.pasada()
        self.iguales()

    def test_repo_solo_de_onedrive_y_quieto(self):
        repo = os.path.join(self.O, UNI, 'P1')
        escribir(os.path.join(repo, '.git', 'HEAD'), 'ref: refs/heads/main')
        escribir(os.path.join(repo, 'main.c'), 'int main(){}')
        inf = self.pasada()                                         # recién tocado: no se copia
        self.assertEqual(sum(inf.copiados.values()), 0)
        self.assertTrue(inf.repos_ocupados)
        for r, _, fs in os.walk(repo):
            for f in fs:
                os.utime(os.path.join(r, f), (VIEJO, VIEJO))
        self.pasada()
        self.iguales()
        # Un cambio dentro del repo en H: no se trae: se repone el de OneDrive y el de H: va a la papelera.
        escribir(os.path.join(self.H, UNI, 'P1', 'main.c'), 'cambiado en H', VIEJO + 100)
        inf = self.pasada()
        self.assertTrue(inf.repos_ignorados)
        self.assertEqual(leer(os.path.join(self.H, UNI, 'P1', 'main.c')), 'int main(){}')
        self.assertEqual(leer(os.path.join(self.O, UNI, 'P1', 'main.c')), 'int main(){}')
        self.assertEqual(len(inf.a_papelera), 1)

    def test_carpeta_movida_a_un_repo_ocupado_no_es_un_borrado(self):
        """El 22-10-2026: repos renombrados en OneDrive, todavía ocupados → 6633 «borrados» retenidos."""
        repo = os.path.join(self.O, UNI, 'P1')
        for f in [os.path.join('.git', 'HEAD'), os.path.join('.git', 'index'), 'main.c'] + \
                 [os.path.join('datos', f'{i}.txt') for i in range(5)]:
            escribir(os.path.join(repo, f), f'contenido de {f}', VIEJO)
        self.pasada()
        self.assertTrue(os.path.exists(os.path.join(self.H, UNI, 'P1', 'datos', '4.txt')))
        nuevo = os.path.join(self.O, UNI, 'Práctica 1')
        os.rename(repo, nuevo)
        escribir(os.path.join(nuevo, '.git', 'index'), 'index nuevo', time.time())   # git lo acaba de tocar
        inf = self.pasada()
        self.assertEqual(inf.retenidos, [])                         # no pide confirmación…
        self.assertEqual(len(inf.esperan_repo), 7)                  # …espera (todo menos el index, que cambió)
        self.assertEqual(len(inf.a_papelera), 2)                    # el index viejo, en G: y en H:
        self.assertTrue(os.path.exists(os.path.join(self.H, UNI, 'P1', 'datos', '4.txt')))
        self.assertFalse(os.path.exists(os.path.join(self.H, UNI, 'Práctica 1')))   # ni crea aún la carpeta
        for r, _, fs in os.walk(nuevo):                             # el repo se queda quieto
            for f in fs:
                os.utime(os.path.join(r, f), (VIEJO, VIEJO))
        inf = self.pasada()
        self.assertEqual((inf.movidos['G:'], inf.movidos['H:'], inf.copiados['G:'], inf.a_papelera), (1, 1, 1, []))
        self.assertFalse(os.path.exists(os.path.join(self.H, UNI, 'P1')))
        self.iguales()

    def test_archivo_vacio_no_se_propaga(self):
        escribir(os.path.join(self.H, UNI, 'Mates', 'Tema 2.pdf'), '')          # p. ej. un fallo de Drive
        inf = self.pasada()
        self.assertTrue(any('vacío' in a for a in inf.avisos))
        self.assertEqual(leer(os.path.join(self.O, UNI, 'Mates', 'Tema 2.pdf')), 'tema 2')
        self.assertEqual(leer(os.path.join(self.G, UNI, 'Mates', 'Tema 2.pdf')), 'tema 2')

    def test_lo_que_llega_de_una_copia_aparta_antes_la_version_de_onedrive(self):
        escribir(os.path.join(self.H, UNI, 'Mates', 'Tema 3.pdf'), 'tema 3 cambiado en H')
        inf = self.pasada()
        apartado = [p['ruta'] for p in inf.pasos if p['ruta'].startswith(self.O)]
        self.assertEqual(len(apartado), 1)                       # la de OneDrive, a la Papelera antes de sustituirla
        self.assertTrue(papelera.buscar(apartado[0]))
        self.assertEqual(leer(os.path.join(self.O, UNI, 'Mates', 'Tema 3.pdf')), 'tema 3 cambiado en H')

    def test_nada_que_no_quepa_en_la_papelera(self):
        os.remove(os.path.join(self.H, UNI, 'Mates', 'Tema 1.pdf'))
        with mock.patch.object(papelera, 'capacidad_papelera', lambda ruta: 3):  # una Papelera de 3 bytes
            inf = self.pasada()
        self.assertTrue(any('no cabe en la Papelera' in e for e in inf.errores))
        self.assertTrue(os.path.exists(os.path.join(self.O, UNI, 'Mates', 'Tema 1.pdf')))   # no se ha borrado
        self.pasada()                                             # con Papelera normal, ya sí
        self.iguales()

    def test_carpeta_renombrada_si_lo_viejo_no_cabe_en_la_papelera(self):
        """Si lo que iba antes a la papelera no se puede mandar, no se renombra: archivo a archivo, y lo viejo se queda."""
        os.rename(os.path.join(self.O, UNI, 'Mates'), os.path.join(self.O, UNI, 'Matemàtiques'))
        escribir(os.path.join(self.O, UNI, 'Matemàtiques', 'Tema 1.pdf'), 'tema 1 nuevo')
        with mock.patch.object(papelera, 'capacidad_papelera', lambda ruta: 3):
            inf = self.pasada()
        self.assertEqual((inf.movidos['G:'], inf.movidos['H:']), (5, 5))
        self.assertTrue(any('no cabe en la Papelera' in e for e in inf.errores))
        self.assertEqual(leer(os.path.join(self.G, UNI, 'Mates', 'Tema 1.pdf')), 'tema 1')   # no se ha perdido
        self.pasada()                                             # con Papelera normal, ya sí
        self.assertFalse(os.path.exists(os.path.join(self.G, UNI, 'Mates')))
        self.iguales()

    def test_simulacion_no_toca_nada(self):
        escribir(os.path.join(self.O, UNI, 'nuevo.pdf'), 'nuevo')
        os.remove(os.path.join(self.H, OTRA, 'nota.txt'))
        antes = (arbol(self.O), arbol(self.G), arbol(self.H))
        inf = self.pasada(simulacion=True)
        self.assertTrue(inf.plan)
        self.assertEqual((arbol(self.O), arbol(self.G), arbol(self.H)), antes)
        self.assertEqual(self.pasada(simulacion=True).plan, inf.plan)  # el estado no ha cambiado


class Interfaz(Base):
    """Lo que la interfaz pide al sincronizador nunca espera a que acabe una pasada (el cuelgue del 22-10-2026)."""

    def retener(self):
        for i in range(5):                                         # max_borrados = 3 en estas pruebas
            os.remove(os.path.join(self.H, UNI, 'Mates', f'Tema {i}.pdf'))
        return [S.clave(r) for r, _ in self.pasada().retenidos]

    def test_decidir_no_espera_a_la_pasada(self):
        claves = self.retener()
        with self.s._lock:                                         # como si hubiera una pasada en marcha
            t = threading.Thread(target=self.s.decidir, args=(claves, 'borrar'))
            t.start()
            t.join(5)
            self.assertFalse(t.is_alive())
        self.assertEqual(len(self.pasada().a_papelera), 10)
        self.iguales()

    def test_decision_durante_una_pasada_vale_para_la_siguiente(self):
        claves = self.retener()
        real = self.s._ejecutar

        def ejecutar_y_decidir(*a, **kw):                          # el usuario pulsa mientras la pasada trabaja
            self.s.decidir(claves, 'borrar')
            return real(*a, **kw)
        with mock.patch.object(self.s, '_ejecutar', ejecutar_y_decidir):
            inf = self.pasada()
        self.assertEqual(len(inf.retenidos), 5)                    # esa pasada ya había leído las decisiones…
        self.assertEqual(set(self.s.decisiones()), set(claves))    # …y no borra las nuevas
        self.assertEqual(len(self.pasada().a_papelera), 10)
        self.iguales()

    def test_ultima_pasada_sin_tocar_la_base(self):
        self.pasada()
        t = self.s.ultima()
        self.assertAlmostEqual(t, time.time(), delta=60)
        with mock.patch.object(self.s, 'db', None):
            self.assertEqual(self.s.ultima(), t)
        otro = S.Sincronizador(self.cfg)
        self.assertEqual(otro.ultima(), t)
        otro.db.close()


if __name__ == '__main__':
    unittest.main()
