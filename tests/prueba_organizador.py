"""Prueba de punta a punta en la carpeta de pruebas: descargas → ventanitas → botones → deshacer.

    python tests/crear_sandbox.py pruebas
    python tests/prueba_organizador.py pruebas <carpeta para capturas>

Abre el programa de verdad (con la config de pruebas), simula las descargas con su origen web,
espera a cada ventanita, guarda una captura, pulsa lo que toque y comprueba el resultado.
"""
import glob
import os
import shutil
import sys
import time
import traceback
import unicodedata
import zipfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import pymupdf  # noqa: E402
from PIL import Image  # noqa: E402

from organizador import app as A  # noqa: E402
from organizador import config  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utiles import captura, zona  # noqa: E402

_REAL = config.cargar()
REAL_UNI = os.path.join(_REAL.onedrive, _REAL.universidad)
SANDBOX = os.path.abspath(sys.argv[1])
CAPTURAS = os.path.abspath(sys.argv[2])
os.makedirs(CAPTURAS, exist_ok=True)
DESC = os.path.join(SANDBOX, 'Downloads')
OD = os.path.join(SANDBOX, 'OneDrive')
UNI = os.path.join(OD, '1 - Universidad UPF')
resultados: list[tuple[bool, str]] = []


def ok(cond, texto):
    resultados.append((bool(cond), texto))
    print(('OK   ' if cond else 'FALLO') + ' ' + texto, flush=True)


def pdf(ruta, titulo, texto):
    d = pymupdf.open()
    p = d.new_page()
    p.insert_text((72, 90), titulo, fontsize=22)
    p.insert_text((72, 140), texto, fontsize=11)
    d.save(ruta)


def real(rel):
    return os.path.join(REAL_UNI, rel)


# ── Las descargas de prueba ─────────────────────────────────────────────────
def descargar(clave):
    """Copia a Descargas un archivo de prueba, como lo haría el navegador."""
    ag = 'https://aulaglobal.upf.edu'
    if clave == 'A':   # Tema de Càlcul I, curso conocido; el nombre del archivo es críptico
        r = os.path.join(DESC, '6357405_tema2_ca_15.09.2026.10.11.12.123.pdf')
        shutil.copyfile(real(r'1r - T1 - Càlcul I\1 - Teoría\Tema 2 - Usos de la derivada.pdf'), r)
        zona(r, f'{ag}/course/view.php?id=0', f'{ag}/pluginfile.php/6357405/course/section/887469/tema2_ca.pdf')
    elif clave == 'B':  # Apuntes de Aprenentatge Automàtic, curso y recurso desconocidos
        r = os.path.join(DESC, '1456_EXPS_resolucionAdaptacion_15.09.2026.14.29.49.813.pdf')
        shutil.copyfile(real(r'2n - T3 - Aprenentatge Automàtic\1 - Teoría\Tema 07 - Intro to deep learning II.pdf'), r)
        zona(r, f'{ag}/course/view.php?id=95555', f'{ag}/pluginfile.php/99999999/mod_resource/content/2/x.pdf')
    elif clave == 'C':  # Idéntico a uno que ya existe
        r = os.path.join(DESC, 'Examen_parcial_2024 (1).pdf')
        shutil.copyfile(real(r'1r - T2 - Càlcul II\5 - Exámenes\2023-24 - Parcial - Soluciones.pdf'), r)
    elif clave == 'D':  # ZIP de prácticas, de una tarea conocida de Xarxes, con nombres NFD y basura de Mac
        r = os.path.join(DESC, 'P3.zip')
        with zipfile.ZipFile(r, 'w') as z:
            z.writestr('P3/main.c', 'int main(void) { return 0; }\n')
            z.writestr('P3/Makefile', 'all:\n\tcc main.c\n')
            z.writestr(unicodedata.normalize('NFD', 'P3/Pràctica 3 - Enunciat.txt'), 'enunciat')
            z.writestr('__MACOSX/P3/._main.c', 'x')
        zona(r, f'{ag}/mod/assign/view.php?id=1548828', f'{ag}/pluginfile.php/1/mod_assign/intro/P3.zip')
    elif clave == 'E':  # De una web aprendida (inglés)
        r = os.path.join(DESC, 'phrasal-verbs.pdf')
        pdf(r, 'Phrasal verbs with GET', 'get up, get over, get along with')
        zona(r, 'https://dictionary.cambridge.org/grammar/british-grammar/', 'https://cdn.cambridge.org/x.pdf')
    elif clave == 'F':  # Sin pistas
        r = os.path.join(DESC, 'IMG_2034.jpg')
        Image.new('RGB', (64, 48), (200, 80, 80)).save(r)
    elif clave == 'G':  # Como Chrome: primero .crdownload, luego se renombra
        tmp = os.path.join(DESC, 'Unconfirmed 81723.crdownload')
        with open(tmp, 'wb') as f:
            f.write(b'%PDF-1.4 a medias')
        time.sleep(2)
        r = os.path.join(DESC, 'Tema1_ca.pdf')
        shutil.copyfile(real(r"1r - T1 - Càlcul I\1 - Teoría\Tema 1 - Derivada d'una funció.pdf"), tmp)
        os.replace(tmp, r)
        zona(r, f'{ag}/course/view.php?id=0', f'{ag}/pluginfile.php/6357405/course/section/887469/tema1_ca.pdf')
    return r


# ── Guion ───────────────────────────────────────────────────────────────────
def guion(app):
    """Se ejecuta en un hilo aparte; toca las ventanas a través de app.en_ui."""
    import threading
    hecho = threading.Event()

    def ui(f):
        caja = {}

        def envolver():
            try:
                caja['r'] = f()
            except Exception as e:
                caja['e'] = e
            hecho.set()
        hecho.clear()
        app.en_ui(envolver)
        hecho.wait(20)
        if 'e' in caja:
            raise caja['e']
        return caja.get('r')

    def esperar(cond, segundos=40):
        fin = time.time() + segundos
        while time.time() < fin:
            if ui(cond):
                return True
            time.sleep(0.3)
        return False

    def ventana(nombre_archivo):
        ok(esperar(lambda: app.ventana is not None and os.path.basename(app.ventana.s.archivo) == nombre_archivo),
           f'aparece la ventanita de «{nombre_archivo}»')
        time.sleep(0.8)
        v = app.ventana
        datos = ui(lambda: (v.carpeta, v.e_nombre.get(), v.ext, [a.texto for a in v.avisos],
                            v.b_descartar.winfo_ismapped(), v.s.motivo, v.s.seguro,
                            captura(v, os.path.join(CAPTURAS, f'{nombre_archivo}.png'))))
        carpeta, nombre, ext, avisos, descartar, motivo, seguro, (dentro, caja, pantalla) = datos
        ok(dentro, f'la ventanita cabe en la pantalla {caja} ⊂ {pantalla}')
        print(f'      carpeta: {os.path.relpath(carpeta, OD)}\n      nombre : {nombre}{ext}\n      motivo : {motivo}'
              f' (seguro={seguro})\n      avisos : {avisos}\n      descartar visible: {descartar}', flush=True)
        return v, carpeta, nombre, ext, avisos, descartar

    try:
        ok(esperar(lambda: app.perfil.listo, 120), 'el índice de la carpeta de pruebas está listo')

        # A: tema de un curso conocido
        descargar('A')
        v, carpeta, nombre, ext, avisos, _ = ventana('6357405_tema2_ca_15.09.2026.10.11.12.123.pdf')
        ok(carpeta.endswith(r'1r - T1 - Càlcul I\1 - Teoría'), 'A: carpeta Càlcul I › Teoría')
        ok(nombre.startswith('Tema 2'), f'A: el nombre empieza por «Tema 2» ({nombre})')
        # Corrijo el nombre a mano: debe avisar de que ya hay uno distinto y ofrecer sustituirlo.
        nombre = 'Tema 2 - Usos de la derivada'
        ui(lambda: (v.e_nombre.delete(0, 'end'), v.e_nombre.insert(0, nombre), v._refrescar()))
        avisos = ui(lambda: [a.texto for a in v.avisos])
        ok(any('distinto' in a for a in avisos), f'A: al poner un nombre que ya existe, avisa de versión nueva ({avisos})')
        ui(v.aceptar)
        destino_a = os.path.join(carpeta, nombre + ext)
        ok(esperar(lambda: os.path.exists(destino_a) and not os.path.exists(
            os.path.join(DESC, '6357405_tema2_ca_15.09.2026.10.11.12.123.pdf'))), 'A: movido y renombrado')

        # B: curso nuevo → lo corrijo yo y debe aprenderlo
        descargar('B')
        v, carpeta, nombre, ext, avisos, _ = ventana('1456_EXPS_resolucionAdaptacion_15.09.2026.14.29.49.813.pdf')
        ok('curso nuevo' in v.s.motivo, 'B: dice que el curso de Aula Global es nuevo')
        ok('Aprenentatge' in carpeta, f'B: aun así adivina Aprenentatge Automàtic ({os.path.relpath(carpeta, OD)})')
        elegida = os.path.join(UNI, '2n - T3 - Aprenentatge Automàtic', '1 - Teoría')
        ui(lambda: v._elegida(elegida))
        nombre_b = ui(lambda: v.e_nombre.get())
        ui(v.aceptar)
        ok(esperar(lambda: os.path.exists(os.path.join(elegida, nombre_b + '.pdf'))), f'B: movido a Teoría como «{nombre_b}.pdf»')
        def aprendido():
            with open(os.path.join(SANDBOX, 'aprendido.txt'), encoding='utf-8') as f:
                return f.read()
        esperar(lambda: 'curso 95555' in aprendido(), 10)      # se escribe justo después de mover
        texto = aprendido()
        ok('curso 95555 = 1 - Universidad UPF\\2n - T3 - Aprenentatge Automàtic' in texto, 'B: aprendido el curso 95555')
        ok('contexto 99999999 = 1 - Universidad UPF\\2n - T3 - Aprenentatge Automàtic\\1 - Teoría' in texto,
           'B: aprendido el recurso 99999999')

        # C: duplicado idéntico → Descartar
        descargar('C')
        v, carpeta, nombre, ext, avisos, descartar = ventana('Examen_parcial_2024 (1).pdf')
        ok(any('idéntico' in a for a in avisos) and descartar, 'C: detecta el idéntico y ofrece Descartar')
        ok(carpeta.endswith(r'Càlcul II\5 - Exámenes') and nombre == '2023-24 - Parcial - Soluciones',
           'C: sugiere la carpeta y el nombre de la copia que ya tiene')
        ui(v.descartar)
        ok(esperar(lambda: not os.path.exists(os.path.join(DESC, 'Examen_parcial_2024 (1).pdf'))), 'C: a la Papelera')

        # D: ZIP
        descargar('D')
        v, carpeta, nombre, ext, avisos, _ = ventana('P3.zip')
        ok(carpeta.endswith(r'1r - T3 - Xarxes\4 - Prácticas'), 'D: carpeta de la tarea conocida (Xarxes › Prácticas)')
        ok(nombre == 'P3' and ext == '', 'D: se descomprime en una carpeta «P3»')
        ui(v.aceptar)
        dest_d = os.path.join(carpeta, 'P3')
        ok(esperar(lambda: os.path.exists(os.path.join(dest_d, 'main.c'))), 'D: descomprimido')
        nombres = os.listdir(dest_d) if os.path.isdir(dest_d) else []
        ok('Pràctica 3 - Enunciat.txt' in nombres and all(unicodedata.is_normalized('NFC', n) for n in nombres),
           f'D: nombres en NFC, sin __MACOSX ({nombres})')
        ok(esperar(lambda: not os.path.exists(os.path.join(DESC, 'P3.zip'))), 'D: el zip, a la Papelera')

        # E: web aprendida
        descargar('E')
        v, carpeta, nombre, ext, avisos, _ = ventana('phrasal-verbs.pdf')
        ok('6 - Idiomas' in carpeta, f'E: va a Idiomas por la web ({os.path.relpath(carpeta, OD)})')
        ok(nombre == 'Phrasal verbs with GET', f'E: nombre del título del PDF ({nombre})')
        ui(v.aceptar)

        # F: sin pistas → Más tarde
        descargar('F')
        v, carpeta, nombre, ext, avisos, _ = ventana('IMG_2034.jpg')
        ui(v.mas_tarde)
        ok(esperar(lambda: any(os.path.basename(r) == 'IMG_2034.jpg' for r, *_ in app.pendientes())),
           'F: «Más tarde» lo deja en Pendientes')
        time.sleep(4)
        ok(ui(lambda: app.ventana is None), 'F: no vuelve a salir solo')

        # G: descarga a medias (.crdownload) y luego terminada
        descargar('G')
        v, carpeta, nombre, ext, avisos, _ = ventana('Tema1_ca.pdf')
        ok(nombre.startswith('Tema 1') and 'alculus' not in nombre, f'G: «{nombre}»')
        ok(any('distinto' in a for a in avisos) or nombre != "Tema 1 - Derivada d'una funció",
           'G: si coincide con el Tema 1 que ya hay, avisa de versión nueva')
        ui(v.aceptar)
        ok(esperar(lambda: not os.path.exists(os.path.join(DESC, 'Tema1_ca.pdf'))), 'G: movido; el antiguo, a la Papelera')

        # Pendientes e historial en pantalla
        ui(app.abrir_pendientes)
        time.sleep(1.5)
        for clave in ('pendientes', 'historial'):
            if clave == 'historial':
                ui(app.abrir_historial)
                time.sleep(1.5)
            w = app.ventanas_aux[clave]
            ui(lambda: captura(w, os.path.join(CAPTURAS, f'_{clave}.png')))

        # Deshacer todo, de lo último a lo primero
        filas = app.historial.lista()
        for id_, _f, _t, desc, estado in filas:
            if estado == 'hecho':
                try:
                    app.ejecutor.deshacer(id_)
                    ok(True, f'deshacer: {desc}')
                except Exception as e:
                    ok(False, f'deshacer: {desc} → {e}')
        quedan = sorted(os.listdir(DESC))
        esperado = sorted(['6357405_tema2_ca_15.09.2026.10.11.12.123.pdf',
                           '1456_EXPS_resolucionAdaptacion_15.09.2026.14.29.49.813.pdf', 'Examen_parcial_2024 (1).pdf',
                           'P3.zip', 'phrasal-verbs.pdf', 'IMG_2034.jpg', 'Tema1_ca.pdf'])
        ok(quedan == esperado, f'tras deshacer, Descargas vuelve a estar como antes ({quedan})')
        ok(not os.path.exists(dest_d), 'tras deshacer, la carpeta P3 descomprimida ya no está')
        ok(os.path.exists(os.path.join(UNI, r'1r - T1 - Càlcul I\1 - Teoría\Tema 2 - Usos de la derivada.pdf')),
           'tras deshacer, el Tema 2 antiguo ha vuelto de la Papelera')
        time.sleep(3)
        ok(ui(lambda: app.ventana is None and not app.por_mostrar), 'lo deshecho no vuelve a abrir ventanitas')
    except Exception:
        traceback.print_exc()
        ok(False, 'el guion no terminó')
    finally:
        app.en_ui(app.salir)


def main():
    cfg = config.cargar(os.path.join(SANDBOX, 'config.toml'))
    A.configurar_registro(cfg)
    app = A.App(cfg)
    import threading
    threading.Thread(target=guion, args=(app,), daemon=True).start()
    app.correr()
    fallos = [t for b, t in resultados if not b]
    print(f'\n{len(resultados) - len(fallos)} de {len(resultados)} comprobaciones bien.')
    sys.exit(1 if fallos else 0)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
