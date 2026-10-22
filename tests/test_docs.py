"""Copias Word de los Google Docs, con manifiestos simulados.  python -m unittest tests.test_docs

Carpetas locales que hacen de OneDrive, G:, H: y de «_exportados_docs» de cada cuenta. Lo que va a la
Papelera durante la prueba se recupera al final.
"""
import json
import os
import shutil
import stat
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from organizador import papelera
from organizador import sincro as S
from organizador.config import Config
from organizador.docs_word import Words
from organizador.sugeridor import Sugeridor, Sugerencia
from organizador.origen import Origen
from organizador.contenido import Contenido

UNI = '1 - Uni'
VIEJO = time.time() - 3 * 86400


def escribir(ruta, datos, mtime=None):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, 'wb' if isinstance(datos, bytes) else 'w') as f:
        f.write(datos)
    if mtime:
        os.utime(ruta, (mtime, mtime))


def leer(ruta):
    with open(ruta, 'rb') as f:
        return f.read()


class Docs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='docs')
        j = os.path.join
        self.O, self.G, self.H = j(self.tmp, 'O'), j(self.tmp, 'G'), j(self.tmp, 'H')
        self.EG = j(self.G, '_exportados_docs')
        for r in (self.O, self.G, self.H):
            escribir(j(r, UNI, 'Mates', 'Tema 1.pdf'), 'tema 1', VIEJO)
        self.cfg = Config(descargas=j(self.tmp, 'D'), onedrive=self.O, universidad=UNI, carpetas_indice=[UNI],
                          datos=j(self.tmp, 'datos'), sincro_simulacion=False, max_borrados=20, minutos_repo=10,
                          copias=[{'nombre': 'G:', 'raiz': self.G, 'carpetas': [UNI]},
                                  {'nombre': 'H:', 'raiz': self.H, 'carpetas': [UNI]}],
                          cuentas_docs=[{'copia': 'G:', 'exportados': self.EG}])
        os.makedirs(self.cfg.datos)
        self.s = S.Sincronizador(self.cfg)
        self.assertTrue(self.s.crear_estado_inicial()[0])
        self.w = Words(self.cfg)
        self.docs = {}
        self.papeleras = []

    def tearDown(self):
        for p in self.papeleras:
            try:
                papelera.restaurar(p['ruta'], p['fecha'])
            except OSError:
                pass
        self.s.db.close()
        self.w.db.close()
        for r, ds, fs in os.walk(self.tmp):
            for f in fs:
                os.chmod(os.path.join(r, f), stat.S_IWRITE | stat.S_IREAD)
        shutil.rmtree(self.tmp, ignore_errors=True)

    # El «script de Google» simulado
    def exportar(self, id_, nombre, ruta, contenido):
        escribir(os.path.join(self.EG, id_ + '.docx'), contenido)
        self.docs[id_] = {'nombre': nombre, 'ruta': ruta, 'modificado': str(time.time()), 'exportado': str(time.time())}
        self._manifiesto()

    def quitar(self, id_):
        self.docs.pop(id_)
        self._manifiesto()

    def _manifiesto(self):
        escribir(os.path.join(self.EG, 'manifest.json'), json.dumps({'version': 1, 'docs': self.docs}))

    def pasada(self):
        """Como en el programa: primero los Word, luego la sincronización."""
        inf_d = self.w.actualizar()
        self.s.excluir(self.w.excluidas())
        inf = self.s.pasada()
        self.papeleras += inf_d.pasos + inf.pasos
        return inf_d, inf

    def test_word_nuevo_va_a_onedrive_y_h_pero_no_a_g(self):
        self.exportar('doc1', 'Resumen de límites', f'{UNI}/Mates', b'word v1')
        d, inf = self.pasada()
        word = os.path.join(UNI, 'Mates', 'Resumen de límites.docx')
        self.assertEqual(d.nuevos, [word])
        self.assertEqual(leer(os.path.join(self.O, word)), b'word v1')
        self.assertFalse(os.access(os.path.join(self.O, word), os.W_OK))              # solo lectura
        self.assertEqual(leer(os.path.join(self.H, word)), b'word v1')
        self.assertFalse(os.path.exists(os.path.join(self.G, word)))                 # en G: solo el Doc
        self.assertEqual(self.pasada()[1].resumen(), 'todo igual')

    def test_doc_cambiado_renombrado_y_borrado(self):
        self.exportar('doc1', 'Apuntes', f'{UNI}/Mates', b'v1')
        self.pasada()
        self.exportar('doc1', 'Apuntes', f'{UNI}/Mates', b'v2')                       # cambia el Doc
        d, inf = self.pasada()
        self.assertEqual(len(d.actualizados), 1)
        self.assertEqual(leer(os.path.join(self.H, UNI, 'Mates', 'Apuntes.docx')), b'v2')   # aunque era de solo lectura
        self.docs['doc1'].update(nombre='Apuntes de Mates', ruta=f'{UNI}/Mates/Teoría')      # se renombra y se mueve
        self._manifiesto()
        d, inf = self.pasada()
        nuevo = os.path.join(UNI, 'Mates', 'Teoría', 'Apuntes de Mates.docx')
        self.assertEqual(len(d.movidos), 1)
        self.assertTrue(os.path.exists(os.path.join(self.O, nuevo)) and os.path.exists(os.path.join(self.H, nuevo)))
        self.assertFalse(os.path.exists(os.path.join(self.H, UNI, 'Mates', 'Apuntes.docx')))
        self.assertEqual(sum(inf.copiados.values()), 0)                                     # se movió, no se copió
        self.quitar('doc1')                                                                  # se borra el Doc
        d, inf = self.pasada()
        self.assertEqual(d.a_papelera, [nuevo])
        self.assertFalse(os.path.exists(os.path.join(self.O, nuevo)) or os.path.exists(os.path.join(self.H, nuevo)))

    def test_word_editado_a_mano_no_se_pisa(self):
        self.exportar('doc1', 'Resumen', f'{UNI}/Mates', b'v1')
        self.pasada()
        ruta = os.path.join(self.O, UNI, 'Mates', 'Resumen.docx')
        os.chmod(ruta, stat.S_IWRITE)
        escribir(ruta, b'editado a mano')
        self.exportar('doc1', 'Resumen', f'{UNI}/Mates', b'v2')
        d, _ = self.pasada()
        self.assertEqual(len(d.editados), 1)
        self.assertEqual(leer(ruta), b'v2')
        apartado = os.path.join(self.O, d.editados[0])
        self.assertIn('editado en Word', apartado)
        self.assertEqual(leer(apartado), b'editado a mano')

    def test_nombre_que_choca_con_un_word_de_verdad(self):
        escribir(os.path.join(self.O, UNI, 'Mates', 'Resumen.docx'), b'mi word')
        self.exportar('doc1', 'Resumen', f'{UNI}/Mates', b'del doc')
        d, _ = self.pasada()
        self.assertEqual(d.nuevos, [os.path.join(UNI, 'Mates', 'Resumen (Doc).docx')])
        self.assertEqual(leer(os.path.join(self.O, UNI, 'Mates', 'Resumen.docx')), b'mi word')

    def test_pdf_definitivo_pregunta_y_borra_el_doc(self):
        self.exportar('doc1', 'Trabajo final', f'{UNI}/Mates', b'v1')
        escribir(os.path.join(self.G, UNI, 'Mates', 'Trabajo final.gdoc'), '{"doc_id": "doc1"}')
        self.pasada()
        escribir(os.path.join(self.O, UNI, 'Mates', 'Trabajo final.pdf'), b'%PDF-1.4 definitivo')
        d, _ = self.pasada()
        self.assertEqual([(os.path.basename(r), i) for r, i, _ in d.pdf_definitivos], [('Trabajo final.pdf', 'doc1')])
        ruta_gdoc = self.w.borrar_doc('doc1')
        self.papeleras.append({'ruta': ruta_gdoc, 'fecha': time.time() - 5})
        self.assertFalse(os.path.exists(ruta_gdoc))
        self.w.decidir_pdf(d.pdf_definitivos[0][0], 'borrado')
        self.assertEqual(self.pasada()[0].pdf_definitivos, [])

    def test_pdf_conservar_no_vuelve_a_preguntar(self):
        self.exportar('doc1', 'Informe', f'{UNI}/Mates', b'v1')
        self.pasada()
        escribir(os.path.join(self.O, UNI, 'Mates', 'Informe.pdf'), b'%PDF')
        d, _ = self.pasada()
        self.w.decidir_pdf(d.pdf_definitivos[0][0], 'conservar')
        self.assertEqual(self.pasada()[0].pdf_definitivos, [])

    def test_aviso_en_la_ventanita_de_descarga(self):
        self.exportar('doc1', 'Memoria', f'{UNI}/Mates', b'v1')
        self.pasada()
        sug = Sugeridor(self.cfg, None, None, None)
        sug.words = self.w
        pdf = os.path.join(self.tmp, 'D', 'memoria-final.pdf')
        escribir(pdf, b'%PDF')
        s = Sugerencia(pdf, os.path.join(self.O, UNI, 'Mates'), 'Memoria', '.pdf', '', True, Origen(), Contenido(),
                       'h', 4, duplicados=[])
        avisos = sug.avisos(s, s.carpeta, 'Memoria', False)
        aviso = [a for a in avisos if a.tipo == 'pdf_definitivo']
        self.assertEqual(len(aviso), 1)
        self.assertFalse(aviso[0].marcado)                       # nunca decide solo: la casilla empieza sin marcar


if __name__ == '__main__':
    unittest.main()
