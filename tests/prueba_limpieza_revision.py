"""Prueba de punta a punta de la limpieza de Descargas y la revisión semanal, en la carpeta de pruebas.

    python tests/crear_sandbox.py pruebas
    python tests/prueba_limpieza_revision.py pruebas <carpeta para capturas>

Limpieza de Descargas (aviso el día 6, Papelera el día 7, deshacer) y revisión semanal
(se abre sola, Borrar / Guardar en… / Dejar, Aplicar, deshacer). Para no esperar días,
se adelanta la fecha de llegada en la base de datos del programa de pruebas.
"""
import os
import shutil
import sys
import threading
import time
import traceback

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image  # noqa: E402

from organizador import app as A  # noqa: E402
from organizador import config  # noqa: E402
from organizador.nombres import clave  # noqa: E402
from utiles import captura  # noqa: E402

SANDBOX = os.path.abspath(sys.argv[1])
CAPTURAS = os.path.abspath(sys.argv[2])
os.makedirs(CAPTURAS, exist_ok=True)
DIA = 86400
# Un vídeo cualquiera para la grabación de pantalla de prueba (variable de entorno VIDEO_PRUEBA).
VIDEO = os.environ.get('VIDEO_PRUEBA', '')
resultados = []


def ok(cond, texto):
    resultados.append((bool(cond), texto))
    print(('OK   ' if cond else 'FALLO') + ' ' + texto, flush=True)


def main():
    cfg = config.cargar(os.path.join(SANDBOX, 'config.toml'))
    desc, cap, vid = cfg.descargas, cfg.carpetas_capturas[0], cfg.carpetas_capturas[1]
    # Descargas: uno que llegó hace 6,5 días (toca aviso) y uno de hoy.
    viejo = os.path.join(desc, 'instalador-viejo.exe')
    nuevo = os.path.join(desc, 'horario.pdf')
    for r in (viejo, nuevo):
        with open(r, 'wb') as f:
            f.write(os.urandom(2048))
    # Capturas: 5 viejas (una se guardará, otra se dejará), 1 reciente que no debe salir, y una grabación.
    viejas = []
    for i, color in enumerate([(220, 60, 60), (60, 160, 60), (60, 90, 220), (200, 160, 40), (120, 60, 160)]):
        r = os.path.join(cap, f'Captura de pantalla 2026-10-0{i + 1} 1{i}3000.png')
        Image.new('RGB', (1600, 900), color).save(r)
        viejas.append(r)
    reciente = os.path.join(cap, f'Captura de pantalla {time.strftime("%Y-%m-%d")} 120000.png')
    Image.new('RGB', (800, 450), (0, 0, 0)).save(reciente)
    grabacion = os.path.join(vid, 'Juego 2026-10-03 21-15-02.mp4')
    if VIDEO and os.path.exists(VIDEO):
        shutil.copyfile(VIDEO, grabacion)
    else:
        with open(grabacion, 'wb') as f:
            f.write(os.urandom(4096))
    hace10 = time.time() - 10 * DIA
    os.utime(grabacion, (hace10, hace10))

    A.configurar_registro(cfg)
    app = A.App(cfg)
    h = app.historial
    h.descarga_nueva('instalador-viejo.exe', presentado=True, cuando=time.time() - 6.5 * DIA)
    h.descarga_nueva('horario.pdf', presentado=True)
    avisos = []
    app.bandeja.notificar = lambda titulo, texto: avisos.append(texto)     # sin globos durante la prueba
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
        hecho.wait(30)
        if 'e' in caja:
            raise caja['e']
        return caja.get('r')

    def esperar(cond, s=40):
        fin = time.time() + s
        while time.time() < fin:
            if ui(cond):
                return True
            time.sleep(0.3)
        return False

    def guion():
        try:
            # ── Limpieza ──
            ok(esperar(lambda: avisos != [], 30), f'el día 6 avisa con una notificación: {avisos}')
            ok(os.path.exists(viejo), 'el aviso no tira nada')
            ok(ui(lambda: app.n_avisos()) == 1, 'el icono cuenta 1 que se va mañana')
            ui(app.abrir_pendientes)
            time.sleep(1.5)
            ui(lambda: captura(app.ventanas_aux['pendientes'], os.path.join(CAPTURAS, 'f2_pendientes.png')))
            ui(lambda: app.ventanas_aux['pendientes'].destroy())
            # Pasa un día: la fecha de llegada y la del aviso, un día atrás.
            with h.db:
                h.db.execute('UPDATE descargas SET primera_vez=primera_vez-?, aviso=aviso-? WHERE nombre=?',
                             (DIA, DIA, clave('instalador-viejo.exe')))
            app._limpiar()
            ok(esperar(lambda: not os.path.exists(viejo)), 'el día 7 va a la Papelera')
            ok(os.path.exists(nuevo), 'lo de hoy se queda')
            fila = next(f for f in h.lista() if f[2] == 'limpieza')
            print('      historial:', fila[3])
            app.ejecutor.deshacer(fila[0])
            ok(os.path.exists(viejo), 'Deshacer lo devuelve a Descargas')
            time.sleep(3)
            ok(ui(lambda: app.ventana is None), 'lo devuelto no abre la ventanita de descarga')

            # ── Revisión semanal: se abre sola ──
            ok(esperar(lambda: isinstance(app.ventanas_aux.get('revision'), object) and
                       app.ventanas_aux.get('revision') is not None, 20), 'la revisión semanal se abre sola')
            ventana = app.ventanas_aux['revision']
            v = ventana.capturas                      # la pestaña «Capturas» de la ventana semanal
            ok(ventana.resumen is not None, 'la ventana semanal tiene la pestaña «Resumen»')
            ui(lambda: captura(ventana, os.path.join(CAPTURAS, 'f2_semana_resumen.png')))
            ui(lambda: ventana.pestanas.set(f'Capturas ({len(v.rutas)})'))
            ok(sorted(v.rutas) == sorted(viejas + [grabacion]), f'salen las 5 viejas y la grabación, no la de hoy '
                                                                 f'({len(v.rutas)})')
            ok(all(e == 'Borrar' for e in v.eleccion.values()), 'de entrada, todas marcadas «Borrar»')
            time.sleep(4)                                     # miniaturas
            ui(lambda: captura(ventana, os.path.join(CAPTURAS, 'f2_revision.png')))
            # Guardar en… (rellenando el diálogo como lo haría él)
            destino = os.path.join(cfg.onedrive, '9 - Personal y hogar')
            ui(lambda: v.celdas[viejas[1]]['seg'].set('Guardar en…'))
            ui(lambda: v._elegir(viejas[1], 'Guardar en…'))
            time.sleep(1)
            dlg = next(w for w in ventana.winfo_children() if w.__class__.__name__ == 'DialogoGuardar')
            ui(lambda: captura(dlg, os.path.join(CAPTURAS, 'f2_guardar.png')))
            ui(lambda: dlg._elegida(destino))
            ui(dlg.guardar)
            ui(lambda: (v.celdas[viejas[2]]['seg'].set('Dejar'), v._elegir(viejas[2], 'Dejar')))
            texto = ui(lambda: v.l_resumen.cget('text'))
            ok('4 a la Papelera' in texto and '1 se guarda' in texto and '1 se queda' in texto, f'resumen: {texto}')
            ui(lambda: captura(ventana, os.path.join(CAPTURAS, 'f2_revision_marcada.png')))
            ui(ventana.aplicar)
            guardada = os.path.join(destino, 'Captura 2026-10-02.png')
            ok(esperar(lambda: os.path.exists(guardada)), 'la de «Guardar en…» está en su carpeta con su nombre')
            ok(not any(os.path.exists(r) for r in (viejas[0], viejas[3], viejas[4], grabacion)),
               'las marcadas «Borrar» (también la grabación) van a la Papelera')
            ok(os.path.exists(viejas[2]) and os.path.exists(reciente), 'la dejada y la reciente siguen ahí')
            ok(not app.revision.turno_pendiente(), 'esta semana ya no vuelve a salir')
            ok(app.revision.pendientes() == [viejas[2]], 'la dejada saldrá la semana que viene')
            fila = next(f for f in h.lista() if f[2] == 'revision')
            print('      historial:', fila[3])
            app.ejecutor.deshacer(fila[0])
            ok(all(os.path.exists(r) for r in viejas + [grabacion]) and not os.path.exists(guardada),
               'Deshacer devuelve todas las capturas a su sitio')
            ui(app.abrir_historial)
            time.sleep(1.5)
            ui(lambda: captura(app.ventanas_aux['historial'], os.path.join(CAPTURAS, 'f2_historial.png')))
        except Exception:
            traceback.print_exc()
            ok(False, 'el guion no terminó')
        finally:
            app.en_ui(app.salir)

    threading.Thread(target=guion, daemon=True).start()
    app.correr()
    fallos = [t for b, t in resultados if not b]
    print(f'\n{len(resultados) - len(fallos)} de {len(resultados)} comprobaciones bien.')
    sys.exit(1 if fallos else 0)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
