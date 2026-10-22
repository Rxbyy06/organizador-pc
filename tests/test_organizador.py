"""Pruebas de las reglas (sin tocar carpetas reales).  python -m unittest discover tests"""
import os
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from organizador import aprendizaje, contenido, origen, zips
from organizador import sugeridor as S
from organizador.carpetas import EXAMENES, PRACTICAS, SEMINARIOS, TEORIA
from organizador.nombres import limpiar_original, ruta_valida, sanear


def senales(limpio='', titulos=(), lineas=(), recurso=''):
    return {'limpio': limpio, 'recurso': recurso, 'titulos': list(titulos), 'lineas': list(lineas)}


class Nombres(unittest.TestCase):
    def test_sanear(self):
        self.assertEqual(sanear('Tema 3: Integrals?'), 'Tema 3 - Integrals')
        self.assertEqual(sanear('a/b|c "d" '), "a-b-c 'd'")
        self.assertEqual(sanear('CON'), 'CON_')
        self.assertEqual(sanear('fin. '), 'fin')
        self.assertEqual(sanear('Mate\u0300ries'), 'Matèries')          # NFD → NFC

    def test_limpiar_original(self):
        self.assertEqual(limpiar_original('1456_EXPS_resolucionAdaptacion_15.09.2026.14.29.49.813'),
                         'EXPS resolucion Adaptacion')
        self.assertEqual(limpiar_original('tema0_ca'), 'Tema0 ca')
        self.assertEqual(limpiar_original('apunts (1)'), 'Apunts')

    def test_ruta_valida(self):
        self.assertIsNone(ruta_valida(r'C:\a\b.pdf'))
        self.assertIn('caracteres', ruta_valida('C:\\a\\' + 'x' * 260))
        self.assertIn('no permitidos', ruta_valida(r'C:\a\b?.pdf'))


class Origen(unittest.TestCase):
    def test_aula_global(self):
        o = origen.de_texto('[ZoneTransfer]\nZoneId=3\nReferrerUrl=https://aulaglobal.upf.edu/course/view.php?id=90444\n'
                            'HostUrl=https://aulaglobal.upf.edu/pluginfile.php/123/mod_resource/content/1/tema2_ca.pdf\n')
        self.assertTrue(o.aula_global)
        self.assertEqual((o.curso, o.contexto, o.componente, o.nombre_recurso), ('90444', '123', 'mod_resource', 'tema2_ca.pdf'))
        self.assertEqual(o.claves(), [('contexto', '123'), ('curso', '90444')])

    def test_web(self):
        o = origen.de_texto('ReferrerUrl=https://dictionary.cambridge.org/x\nHostUrl=https://cdn.x.org/a.pdf')
        self.assertEqual(o.claves(), [('web', 'dictionary.cambridge.org')])
        self.assertEqual(origen.de_texto('HostUrl=about:internet').claves(), [])


class Contenido(unittest.TestCase):
    def test_reparar(self):
        self.assertEqual(contenido.reparar('N´umeros Complejos'), 'Números Complejos')
        self.assertEqual(contenido.reparar('V ECTOR S PACES (II)'), 'VECTOR SPACES (II)')
        self.assertEqual(contenido.reparar('ÀLGEBRA I ESTADÍSTICA'), 'ÀLGEBRA I ESTADÍSTICA')
        self.assertEqual(contenido.reparar('F´ ıSICA'), 'FÍSICA')


class Normas(unittest.TestCase):
    def test_categoria(self):
        o = origen.Origen()
        self.assertEqual(S.deducir_categoria('Examen final 2023 solucions', '', o, None), EXAMENES)
        self.assertEqual(S.deducir_categoria('Seminari 3', '', o, None), SEMINARIOS)
        self.assertEqual(S.deducir_categoria('Pràctica final', '', o, None), PRACTICAS)
        self.assertEqual(S.deducir_categoria('tema4 ca', '', o, None), TEORIA)

    def test_curso(self):
        self.assertEqual(S.curso_academico(['Examen 15 de gener de 2025']), '2024-25')
        self.assertEqual(S.curso_academico(['curs 2023/2024']), '2023-24')
        self.assertEqual(S.curso_academico(['final 2025'], trimestre=1), '2025-26')
        self.assertEqual(S.curso_academico(['final 2025'], trimestre=3), '2024-25')
        self.assertEqual(S.curso_academico(['recuperacio 2025'], trimestre=1, recuperacion=True), '2024-25')

    def test_examen(self):
        s = senales('Exam final sol', ['Càlcul II – 2023/2024 Examen final'])
        self.assertEqual(S.componer_nombre(EXAMENES, s, [], 'Càlcul II'), '2023-24 - Final - Soluciones')
        s = senales('parcial1', ['Midterm 1 — 3 November 2025'])
        self.assertEqual(S.componer_nombre(EXAMENES, s, [], 'X', 1), '2025-26 - Parcial 1')

    def test_tema(self):
        s = senales('Tema0 ca', ['Funcions'])
        self.assertEqual(S.componer_nombre(TEORIA, s, ['Tema 1 - Derivada.pdf']), 'Tema 0 - Funcions')
        self.assertEqual(S.componer_nombre(TEORIA, senales('tema 3', ['Integrals']), ['Tema 12 - X.pdf']),
                         'Tema 03 - Integrals')
        self.assertEqual(S.componer_nombre(TEORIA, senales('temes 1 i 2', ['Intro']), []), 'Tema 1-2 - Intro')

    def test_titulo_asignatura(self):
        s = senales('T3', ['Sistemes Operatius', 'Threads and locks'])
        self.assertEqual(S.componer_nombre(TEORIA, s, [], 'Sistemes Operatius'), 'Tema 3 - Threads and locks')
        s = senales('p2', ['FÍSICA — PHYSICS (27057/27188) PRACTICE 2: DAMPED OSCILLATIONS'])
        self.assertEqual(S.componer_nombre(PRACTICAS, s, [], 'Fonaments de Física'), 'Práctica 2 - Damped oscillations')

    def test_seminario(self):
        s = senales('seminari 4 solucions', ['Seminar 4: Recursion'])
        self.assertEqual(S.componer_nombre(SEMINARIOS, s, [], 'AED'), 'Seminario 4 - Recursion - Soluciones')


class Zips(unittest.TestCase):
    def test_nombres_y_estructura(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = os.path.join(d, 'P3.zip')
            with zipfile.ZipFile(ruta, 'w') as z:
                z.writestr('P3/main.c', 'int main(){}')
                z.writestr('P3/Pra\u0301ctica.txt', 'x')         # NFD, como los zips de Mac
                z.writestr('__MACOSX/P3/._main.c', 'x')
                z.writestr('P3/../../malo.txt', 'x')
            info = zips.analizar(ruta)
            self.assertEqual(info.raiz_unica, 'P3')
            self.assertTrue(info.tiene_codigo)
            self.assertEqual(sorted(r for _, r in info.miembros), ['P3\\Práctica.txt', 'P3\\main.c'])
            dest = [d2 for _, d2 in zips.destinos(info, r'C:\x', 'Práctica 3')]
            self.assertIn(r'C:\x\Práctica 3\main.c', dest)


class Aprendido(unittest.TestCase):
    def test_editar_sin_perder_lo_suyo(self):
        with tempfile.TemporaryDirectory() as d:
            arch = os.path.join(d, 'aprendido.txt')
            with open(arch, 'w', encoding='utf-8') as f:
                f.write('# mi comentario\ncurso 1 = A\nweb x.com = B\n')
            a = aprendizaje.Aprendido(arch, d)
            a.aprender({('curso', '1'): 'C', ('curso', '2'): 'D'})
            with open(arch, encoding='utf-8') as f:
                texto = f.read()
            self.assertIn('# mi comentario', texto)
            self.assertIn('curso 1 = C', texto)
            self.assertIn('curso 2 = D', texto)
            self.assertEqual(a.buscar([('web', 'X.com')]), [(('web', 'X.com'), 'B')])


if __name__ == '__main__':
    unittest.main()
