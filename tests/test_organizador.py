"""Pruebas de las reglas (sin tocar carpetas reales).  python -m unittest discover tests"""
import os
import sys
import tempfile
import types
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from organizador import aprendizaje, contenido, origen, zips
from organizador import sugeridor as S
from organizador.acciones import Ejecutor
from organizador.carpetas import EXAMENES, PRACTICAS, SEMINARIOS, TEORIA
from organizador.config import Config
from organizador.huellas import huella
from organizador.nombres import limpiar_original, ruta_valida, sanear
from organizador.perfil import Perfil


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

    # Casos reales de la semana del 21-10-2026, con el nombre que eligió el usuario.
    def test_informe_sin_repetir_seminario_ni_asignatura(self):
        s = senales('Informe Seminari 2 Sistemes Operatius (u100001 i u100002).docx',
                    ['Informe Seminari 2 Sistemes Operatius', 'Exercici 1 Read where a process is born'])
        self.assertEqual(S.componer_nombre(SEMINARIOS, s, [], 'Sistemes Operatius'), 'Seminario 2 - Informe')

    def test_resumen_de_varios_temas(self):
        s = senales('Apuntes de Sistemas Operativos — Temas 1 a 6',
                    ['Sistemas Operativos', 'Del computador al Sistema Operativo'])
        self.assertEqual(S.componer_nombre(TEORIA, s, [], 'Sistemes Operatius'), 'Resumen T1-T6')
        self.assertEqual(S.deducir_categoria('Temas 1 a 6', '', origen.Origen(), None), TEORIA)
        self.assertEqual(S.componer_nombre(TEORIA, senales('Resumen T1-T6'), [], 'X'), 'Resumen T1-T6')

    def test_tema_sin_repetir_el_numero(self):
        s = senales('t5', ['Tema 5: Memòria virtual'])
        self.assertEqual(S.componer_nombre(TEORIA, s, [], 'Sistemes Operatius'), 'Tema 5 - Memòria virtual')

    def test_asignatura_en_otro_idioma(self):
        self.assertEqual(S._sin_frase('Sistemas Operativos', 'Sistemes Operatius'), '')
        self.assertEqual(S._sin_frase('Problemes de Probabilidad y Estadística', 'Probabilitat i Estadística'),
                         'Problemes de')
        self.assertEqual(S._sin_frase('Sistemes de fitxers', 'Sistemes Operatius'), 'Sistemes de fitxers')
        self.assertEqual(S._sin_frase('Àlgebra', 'Àlgebra Lineal'), 'Àlgebra')          # una palabra suelta, no


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

    def test_en_la_uni_la_carpeta_sigue_las_normas(self):
        """«P2.zip» se descomprimió en «P2» y el usuario lo deshizo (23-10-2026): debe ser «Práctica 2»."""
        with tempfile.TemporaryDirectory() as d:
            practicas = os.path.join(d, 'O', 'U', '2n - T1 - Sistemes Operatius', '4 - Prácticas')
            os.makedirs(practicas)
            ruta = os.path.join(d, 'P2.zip')
            with zipfile.ZipFile(ruta, 'w') as z:
                z.writestr('P2.pdf', 'x')
                z.writestr('Code/fibonacci.c', 'int main(){}')
            cfg = Config(descargas=d, onedrive=os.path.join(d, 'O'), universidad='U', datos=d)
            sg = S.Sugeridor(cfg, types.SimpleNamespace(buscar=lambda claves: []), None, Perfil())
            s = sg.sugerir(ruta)
            self.assertEqual(sg.nombre_para(s, practicas), 'Práctica 2')
            self.assertEqual(sg.nombre_para(s, os.path.join(d, 'O', 'Otra')), 'P2')     # fuera de la uni, tal cual


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

    def test_sin_lineas_en_blanco_de_mas(self):
        with tempfile.TemporaryDirectory() as d:
            arch = os.path.join(d, 'aprendido.txt')
            with open(arch, 'w', encoding='utf-8') as f:
                f.write('# cabecera\n\ncurso 1 = A\nweb x.com = B\n')
            a = aprendizaje.Aprendido(arch, d)
            a.aprender({('contexto', '5'): 'C'})
            a.aprender({('contexto', '6'): 'D'})
            with open(arch, encoding='utf-8') as f:
                self.assertEqual(f.read(), '# cabecera\n\ncurso 1 = A\nweb x.com = B\ncontexto 5 = C\ncontexto 6 = D\n')

    def test_web_contradicha_deja_de_decidir(self):
        """Una web que no es genérica pero de la que bajas cosas para sitios distintos: se olvida, no se pisa."""
        with tempfile.TemporaryDirectory() as d:
            arch = os.path.join(d, 'aprendido.txt')
            with open(arch, 'w', encoding='utf-8') as f:
                f.write('# cabecera\nweb x.com = U\\A\ncurso 7 = U\\A\n')
            cfg = Config(descargas=d, onedrive=d, universidad='U', datos=d)
            yo = types.SimpleNamespace(cfg=cfg, aprendido=aprendizaje.Aprendido(arch, d))
            s = types.SimpleNamespace(origen=origen.de_texto('HostUrl=https://x.com/a.pdf'))
            Ejecutor._aprender(yo, s, os.path.join(d, 'U', 'A'))          # el mismo sitio: sigue
            self.assertEqual(yo.aprendido.regla('web', 'x.com'), 'U\\A')
            Ejecutor._aprender(yo, s, os.path.join(d, 'Otra'))             # otro: deja de fiarse
            self.assertIsNone(yo.aprendido.regla('web', 'x.com'))
            self.assertEqual(yo.aprendido.regla('curso', '7'), 'U\\A')     # lo demás, intacto
            Ejecutor._aprender(yo, s, os.path.join(d, 'Otra'))             # sin regla: vuelve a aprender
            self.assertEqual(yo.aprendido.regla('web', 'x.com'), 'Otra')

    def test_web_generica_no_decide_aunque_se_aprendiera(self):
        """El 26-10-2026 aprendió «web claude.ai = …\\1 - Teoría»: todo lo de claude.ai habría ido ahí."""
        with tempfile.TemporaryDirectory() as d:
            teoria = os.path.join(d, 'O', 'U', 'A', '1 - Teoría')
            os.makedirs(teoria)
            arch = os.path.join(d, 'aprendido.txt')
            with open(arch, 'w', encoding='utf-8') as f:
                f.write('web claude.ai = U\\A\\1 - Teoría\nweb cambridge.org = U\\A\\1 - Teoría\n')
            cfg = Config(descargas=d, onedrive=os.path.join(d, 'O'), universidad='U', datos=d,
                         webs_genericas={'claude.ai'})
            sg = S.Sugeridor(cfg, aprendizaje.Aprendido(arch, cfg.onedrive), None, Perfil())
            carpeta, motivo, seguro = sg._donde(origen.de_texto('HostUrl=https://claude.ai/api/files/x'), [])
            self.assertNotEqual(carpeta, teoria)
            self.assertFalse(seguro)
            self.assertNotIn('web nueva', motivo)                    # tampoco promete aprenderla
            carpeta, _, seguro = sg._donde(origen.de_texto('HostUrl=https://cambridge.org/x.pdf'), [])
            self.assertEqual((carpeta, seguro), (teoria, True))       # las demás webs, como siempre

    def test_identico_es_igual(self):
        with tempfile.TemporaryDirectory() as d:
            a, b, c = (os.path.join(d, n) for n in 'abc')
            for ruta, texto in ((a, 'hola'), (b, 'hola'), (c, 'adiós')):
                with open(ruta, 'w', encoding='utf-8') as f:
                    f.write(texto)
            s = types.SimpleNamespace(tam=os.path.getsize(a), hash=huella(a))
            self.assertTrue(S.Sugeridor.es_igual(b, s))
            self.assertFalse(S.Sugeridor.es_igual(c, s))
            self.assertFalse(S.Sugeridor.es_igual(os.path.join(d, 'no'), s))


if __name__ == '__main__':
    unittest.main()
