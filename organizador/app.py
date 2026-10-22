"""Arranque del Organizador: icono, vigilante de Descargas, índice en segundo plano y ventanas."""
import argparse
import logging
import logging.handlers
import os
import queue
import sys
import threading
import time
import traceback
from collections import deque
from tkinter import messagebox

import customtkinter as ctk

from . import aprendizaje, config, sistema
from .acciones import Ejecutor, Historial
from .docs_word import Words
from .bandeja import Bandeja
from .huellas import Indice
from .limpieza import Limpieza, en_descargas
from .perfil import Perfil
from .revision import Revision
from .sincro import Sincronizador
from .sugeridor import Sugeridor
from .vigilante import Vigilante
from .ventanas import VentanaDescarga, VentanaHistorial, VentanaPendientes
from .ventanas_revision import VentanaSemanal
from . import copia, espacio
from .resumen import Resumen
from .ventanas_sincro import VentanaBorrados, VentanaPDF

log = logging.getLogger('organizador')


class App:
    def __init__(self, cfg):
        self.cfg = cfg
        self.historial = Historial(cfg)
        self.indice = Indice(cfg)
        self.perfil = Perfil()
        self.aprendido = aprendizaje.Aprendido(cfg.aprendido, cfg.onedrive, cfg.simulacion)
        self.sugeridor = Sugeridor(cfg, self.aprendido, self.indice, self.perfil)
        self.ejecutor = Ejecutor(cfg, self.historial, self.indice, self.aprendido)
        self.vigilante = Vigilante(cfg, self._llega, self._se_va)
        self.limpieza = Limpieza(cfg, self.historial, self.ejecutor)
        self.revision = Revision(cfg, self.historial)
        self.resumen = Resumen(cfg, self.historial)
        self.espacio: list = []
        self.sincro = Sincronizador(cfg, self.historial, self.indice)
        self.words = Words(cfg, self.indice)
        self.sugeridor.words = self.words
        self._pdfs_vistos: set[str] = set()
        self.bandeja = Bandeja(self)

        ctk.set_appearance_mode('system')
        self.root = ctk.CTk()
        self.root.withdraw()
        self.root.title('Organizador del PC')
        self.root.report_callback_exception = self._error_ui

        self._cola_ui: queue.Queue = queue.Queue()
        self.por_mostrar: deque[str] = deque()
        self.ventana: VentanaDescarga | None = None
        self.preparando = False
        self.mostradas = 0
        self.pausa_hasta = 0.0
        self.ventanas_aux: dict[str, object] = {}
        self.semana_pedida = False                      # toca la revisión semanal (resumen y capturas)
        self.ultima_carpeta_captura: str | None = None
        self._sincro_ya = threading.Event()             # «Sincronizar ahora»
        self.sincronizando = False
        self.sincro_retenidos: list = []
        self._retenidos_vistos: tuple = ()
        self._avisos_vistos: set[str] = set()
        self._parar = threading.Event()

    # ── Hilos ───────────────────────────────────────────────────────────────
    def en_ui(self, f) -> None:
        """Ejecuta f en el hilo de las ventanas."""
        self._cola_ui.put(f)

    def _bucle_ui(self) -> None:
        try:
            while True:
                self._cola_ui.get_nowait()()
        except queue.Empty:
            pass
        except Exception:
            log.exception('Error en la interfaz')
        self._quizas_mostrar()
        self.root.after(300, self._bucle_ui)

    def _error_ui(self, tipo, valor, tb):
        log.error('Error en la interfaz: %s', ''.join(traceback.format_exception(tipo, valor, tb)))

    def ejecutar(self, trabajo, al_terminar=None, que='') -> None:
        """Trabajo en segundo plano; al terminar, el resultado (o el error) vuelve a la interfaz."""
        def hilo():
            try:
                r = trabajo()
            except Exception as e:
                log.exception('Falló: %s', que)
                self.en_ui(lambda: messagebox.showerror('Organizador del PC', f'No se pudo {que}:\n\n{e}'))
                r = None
            if al_terminar:
                self.en_ui(lambda: al_terminar(r))
            self.en_ui(self.bandeja.actualizar)
        threading.Thread(target=hilo, daemon=True).start()

    # ── Descargas ───────────────────────────────────────────────────────────
    def _llega(self, ruta: str) -> None:
        """(hilo del vigilante) Una descarga ha terminado."""
        visto = self.historial.descarga_vista(os.path.basename(ruta))
        if visto and visto[1]:
            return                                      # ya se le enseñó: está en Pendientes
        if not visto:
            self.historial.descarga_nueva(os.path.basename(ruta))
        self.en_ui(lambda: self._encolar(ruta))

    def _se_va(self, ruta: str) -> None:
        self.historial.descarga_fuera(os.path.basename(ruta))
        self.en_ui(lambda: self._quitar_de_cola(ruta))

    def _encolar(self, ruta: str, primero: bool = False) -> None:
        if ruta in self.por_mostrar or (self.ventana and self.ventana.s.archivo == ruta):
            return
        (self.por_mostrar.appendleft if primero else self.por_mostrar.append)(ruta)
        self.bandeja.actualizar()

    def _quitar_de_cola(self, ruta: str) -> None:
        if ruta in self.por_mostrar:
            self.por_mostrar.remove(ruta)
        if self.ventana and self.ventana.s.archivo == ruta and self.ventana.winfo_exists():
            self.ventana.destroy()                      # lo ha movido él a mano
            self._cerrada()
        self.bandeja.actualizar()

    def _quizas_mostrar(self) -> None:
        if self.ventana is not None or self.preparando:
            return
        if not self.por_mostrar:
            if self.semana_pedida and not self.pausado() and not sistema.pantalla_completa():
                self.semana_pedida = False
                self.abrir_semana(auto=True)
            return
        if self.pausado() or sistema.pantalla_completa():
            return                                      # espera: aparecerá al salir del juego o la película
        ruta = self.por_mostrar.popleft()
        if not os.path.exists(ruta):
            return
        self.preparando = True

        def preparar():
            s = self.sugeridor.sugerir(ruta)
            s.duplicados = self.sugeridor.duplicados(s)
            self.sugeridor.junto_al_duplicado(s)
            return s

        def abrir(s):
            self.preparando = False
            if s is None or not os.path.exists(ruta):
                return
            self.mostradas += 1
            total = self.mostradas + len(self.por_mostrar)
            self.ventana = VentanaDescarga(self, s, self.mostradas, total)
        self.ejecutar(preparar, abrir, f'preparar «{os.path.basename(ruta)}»')

    def _cerrada(self) -> None:
        self.ventana = None
        if not self.por_mostrar:
            self.mostradas = 0

    def aceptar(self, s, carpeta, nombre, descomprimir, quitar, ext) -> None:
        self._cerrada()
        self.historial.descarga_nueva(os.path.basename(s.archivo), presentado=True)
        self.ejecutar(lambda: self.ejecutor.aceptar(s, carpeta, nombre, descomprimir=descomprimir,
                                                    quitar=quitar, ext=ext),
                      que=f'mover «{os.path.basename(s.archivo)}»')

    def mas_tarde(self, s) -> None:
        self._cerrada()
        self.historial.descarga_nueva(os.path.basename(s.archivo), presentado=True)
        if self.cfg.simulacion:
            log.info('[simulación] «%s»: más tarde', os.path.basename(s.archivo))
        self.bandeja.actualizar()

    def descartar(self, s) -> None:
        self._cerrada()
        self.historial.descarga_nueva(os.path.basename(s.archivo), presentado=True)
        self.ejecutar(lambda: self.ejecutor.descartar(s), que=f'descartar «{os.path.basename(s.archivo)}»')

    def organizar(self, ruta: str) -> None:
        """Desde Pendientes: volver a abrir la ventanita de un archivo."""
        self._encolar(ruta, primero=True)

    def pendientes(self) -> list[tuple[str, float, float]]:
        """(ruta, cuándo llegó, segundos que le quedan antes de la Papelera) de todo lo de Descargas."""
        res = [(r, *self.limpieza.estado(r)) for r in en_descargas(self.cfg)]
        return sorted(res, key=lambda x: x[1])

    def n_pendientes(self) -> int:
        return len(en_descargas(self.cfg))

    def n_avisos(self) -> int:
        """Lo que se va a la Papelera en menos de un día de aviso."""
        return sum(1 for _, _, q in self.pendientes() if q <= self.cfg.dias_aviso * 86400)

    def _revisar_descargas(self) -> None:
        """Al arrancar: lo que no se le ha enseñado aún, a la cola; lo demás queda en Pendientes."""
        presentes = en_descargas(self.cfg)
        for ruta in presentes:
            visto = self.historial.descarga_vista(os.path.basename(ruta))
            if os.path.isfile(ruta) and not (visto and visto[1]):
                self.vigilante.vigilar(ruta)
        self.historial.descargas_sincronizar([os.path.basename(r) for r in presentes])

    # ── Limpieza y revisión semanal ─────────────────────────────────────────
    def _limpiar(self) -> None:
        """(hilo de fondo) Una vez por hora: avisos de Descargas, Papelera y ¿toca la revisión?"""
        avisados, tirados = self.limpieza.revisar()
        if avisados and self.cfg.notificar:
            n = len(avisados)
            self.bandeja.notificar('Descargas', f'Mañana va{"n" if n > 1 else ""} a la Papelera {n} '
                                                f'archivo{"s" if n > 1 else ""} de Descargas. '
                                                f'Míralo{"s" if n > 1 else ""} en Pendientes '
                                                '(icono junto al reloj).')
        if tirados:
            log.info('Limpieza: %d a la Papelera', len(tirados))
        self._mirar_espacio()
        if self.revision.turno_pendiente():
            self.semana_pedida = True
            if self.cfg.carpeta_copia and self.historial.leer_estado('ultima_copia') < self.revision.ultimo_turno():
                try:
                    zip_, quitadas = copia.hacer_copia(self.cfg)
                    self.historial.poner_estado('ultima_copia', time.time())
                    log.info('Copia semanal: %s (%d antiguas a la papelera)', zip_, len(quitadas))
                except Exception:
                    log.exception('Falló la copia semanal')
        self.en_ui(self._refrescar_aux)

    def _mirar_espacio(self) -> None:
        self.espacio = espacio.medir(self.cfg)
        hoy = time.strftime('%Y-%m-%d')
        for u in self.espacio:
            if u.aviso:
                self._avisar_una_vez(f'espacio {u.sitio} {hoy}', 'Espacio', f'{u.texto()}. Libera sitio para que '
                                     'se siga sincronizando sin problemas.')

    def _refrescar_aux(self) -> None:
        v = self.ventanas_aux.get('pendientes')
        if v is not None and v.winfo_exists():
            v.pintar()
        self.bandeja.actualizar()

    def n_revision(self) -> int:
        return len(self.revision.pendientes())

    def abrir_revision(self) -> None:
        self.abrir_semana(auto=False)

    def pendientes_resumen(self) -> list[str]:
        p = []
        if n := self.n_pendientes():
            p.append(f'{n} cosa(s) en Descargas (Pendientes)')
        if self.sincro_retenidos:
            p.append(f'{len(self.sincro_retenidos)} borrados de la sincronización esperan tu confirmación')
        return p

    def abrir_semana(self, auto: bool) -> None:
        """Los lunes (o cuando la pides): pestaña «Resumen» y, si hay capturas viejas, «Capturas»."""
        v = self.ventanas_aux.get('revision')
        if v is not None and v.winfo_exists():
            v.deiconify()
            v.lift()
            return
        if not self.espacio:
            self.espacio = espacio.medir(self.cfg)
        capturas = self.revision.pendientes()
        d = self.resumen.datos(self.pendientes_resumen(), len(capturas), self.espacio)
        if auto and not d.notable:
            self.bandeja.notificar('Revisión semanal', 'Semana sin novedades: todo en orden.')
            self.resumen.hecho(d)
            self.revision.hecha()
            return
        self.ventanas_aux['revision'] = VentanaSemanal(self, d, capturas)

    def aplicar_semana(self, datos, borrar, guardar, dejar) -> None:
        for r in dejar:
            self.revision.dejar(r)
        self.revision.hecha()
        self.resumen.hecho(datos)
        if borrar or guardar:
            self.ejecutar(lambda: self.ejecutor.revisar_capturas(borrar, guardar), que='aplicar la revisión')
        else:
            self.bandeja.actualizar()

    def tirar_duplicado(self, ruta: str) -> None:
        self.ejecutar(lambda: self.ejecutor.tirar(ruta, 'duplicado'), que='mandar el duplicado a la Papelera')

    def posponer_revision(self) -> None:
        self.revision.posponer()
        self.bandeja.actualizar()

    # ── Historial ───────────────────────────────────────────────────────────
    def deshacer(self, id_: int, al_terminar=None) -> None:
        self.ejecutar(lambda: self.ejecutor.deshacer(id_), lambda r: al_terminar and al_terminar(), 'deshacer')

    # ── Pausa y estado ──────────────────────────────────────────────────────
    def pausado(self) -> bool:
        return time.time() < self.pausa_hasta

    def pausar(self, segundos: float | None) -> None:
        self.pausa_hasta = float('inf') if segundos is None else time.time() + segundos
        log.info('En pausa %s', 'indefinida' if segundos is None else f'{segundos / 3600:.0f} h')
        self.en_ui(self.bandeja.actualizar)

    def reanudar(self) -> None:
        self.pausa_hasta = 0
        self.en_ui(self.bandeja.actualizar)

    def texto_estado(self) -> str:
        hechos, total = self.indice.progreso()
        partes = []
        if self.cfg.simulacion:
            partes.append('Simulación (no mueve nada)')
        partes.append(self.texto_sincro())
        partes += [u.texto() for u in self.espacio if u.aviso]
        if total and hechos < total:
            partes.append(f'Índice: {hechos:,} de {total:,}'.replace(',', '.'))
        else:
            partes.append(f'Índice al día ({total:,} archivos)'.replace(',', '.'))
        return ' · '.join(partes)

    def abrir_pendientes(self) -> None:
        self._abrir_aux('pendientes', VentanaPendientes)

    def abrir_historial(self) -> None:
        self._abrir_aux('historial', VentanaHistorial)

    def _abrir_aux(self, clave, clase):
        v = self.ventanas_aux.get(clave)
        if v is not None and v.winfo_exists():
            v.pintar()
            v.deiconify()
            v.lift()
            v.focus_force()
            return
        self.ventanas_aux[clave] = clase(self)

    def abrir_archivo(self, ruta: str) -> None:
        if not os.path.exists(ruta):
            open(ruta, 'a', encoding='utf-8').close()
        os.startfile(ruta)

    # ── Sincronización ──────────────────────────────────────────────────────
    def texto_sincro(self) -> str:
        if self.sincronizando:
            return 'Sincronizando…'
        if self.sincro_retenidos:
            return f'Sincronización en pausa: {len(self.sincro_retenidos)} borrados por confirmar'
        ultima = self.sincro.ultima()
        if not ultima:
            return 'Sin sincronizar todavía'
        minutos = int((time.time() - ultima) // 60)
        cuando = 'ahora mismo' if minutos < 1 else f'hace {minutos} min' if minutos < 120 else f'hace {minutos // 60} h'
        return ('Simulación de sincronización ' if self.cfg.sincro_simulacion else 'Sincronizado ') + cuando

    def sincronizar_ahora(self) -> None:
        self._sincro_ya.set()

    def abrir_borrados(self) -> None:
        v = self.ventanas_aux.get('borrados')
        if v is not None and v.winfo_exists():
            v.lift()
            return
        if self.sincro_retenidos:
            self.ventanas_aux['borrados'] = VentanaBorrados(self, self.sincro_retenidos)

    def _hilo_sincro(self) -> None:
        sistema.hilo_en_segundo_plano()
        self._parar.wait(90)                         # que el PC acabe de arrancar (y Drive de conectarse)
        while not self._parar.is_set():
            pedida = self._sincro_ya.is_set()
            self._sincro_ya.clear()
            if self.pausado() or (not pedida and (sistema.pantalla_completa() or sistema.bateria_baja())):
                self._sincro_ya.wait(300)
                continue
            try:
                self._una_pasada()
            except Exception:
                log.exception('Falló la sincronización')
            self._sincro_ya.wait(self.cfg.sincro_minutos * 60)

    def _copias_word(self) -> None:
        """Antes de cada pasada: los Word de los Docs, del manifiesto de cada cuenta a OneDrive."""
        if not self.cfg.cuentas_docs:
            return
        inf = self.words.actualizar()
        self.sincro.excluir(self.words.excluidas())
        if inf.hubo_cambios:
            log.info('Copias Word: %s', inf.resumen())
            self.historial.registrar('docs', 'Copias Word de los Docs: ' + inf.resumen(), inf.pasos, 'hecho')
            self.historial.apuntar('docs', {'nuevos': inf.nuevos, 'actualizados': inf.actualizados,
                                            'movidos': inf.movidos, 'a_papelera': inf.a_papelera,
                                            'editados': inf.editados})
        if inf.editados:
            self.bandeja.notificar('Copias Word', f'Alguien editó {len(inf.editados)} Word de un Google Doc; no lo he '
                                                  'pisado: está apartado como «… (editado en Word fecha)». '
                                                  'Recuerda editar siempre el Doc.')
        for aviso in inf.avisos:
            self._avisar_una_vez(aviso, 'Copias Word', aviso)
        nuevos = [c for c in inf.pdf_definitivos if c[0] not in self._pdfs_vistos]
        if nuevos:
            self._pdfs_vistos |= {c[0] for c in nuevos}
            self.en_ui(lambda: VentanaPDF(self, nuevos))

    def borrar_doc(self, id_: str, ruta_pdf: str | None = None) -> None:
        """El PDF es la versión definitiva: el Doc editable a la papelera de Drive (su Word lo sigue)."""
        def trabajo():
            ruta = self.words.borrar_doc(id_)
            if ruta_pdf:
                self.words.decidir_pdf(ruta_pdf, 'borrado')
            self.historial.registrar('docs', f'Doc «{os.path.splitext(os.path.basename(ruta))[0]}» a la papelera de Drive '
                                             '(su versión definitiva es un PDF). Se recupera desde la papelera de '
                                             'drive.google.com.', [], 'nota')
            self.sincronizar_ahora()
        self.ejecutar(trabajo, que='borrar el Doc')

    def _una_pasada(self) -> None:
        try:
            self._copias_word()
        except Exception:
            log.exception('Falló lo de las copias Word')
        if not self.sincro.inicializado():
            ok, msg = self.sincro.crear_estado_inicial()
            log.info('Sincronización, estado inicial: %s', msg)
            if not ok:
                self._avisar_una_vez('inicial', 'Sincronización', 'Aún no puedo empezar a sincronizar: ' + msg.split('\n')[0])
                return
        self.sincronizando = True
        self.en_ui(self.bandeja.actualizar)
        try:
            inf = self.sincro.pasada()
        finally:
            self.sincronizando = False
        log.info('Sincronización%s (%.0f s): %s', ' [simulación]' if inf.simulacion else '', inf.segundos, inf.resumen())
        with open(os.path.join(self.cfg.datos, 'sincro_plan.txt'), 'w', encoding='utf-8') as f:
            f.write(f'Última pasada {time.strftime("%Y-%m-%d %H:%M")}{" (SIMULACIÓN)" if inf.simulacion else ""}: '
                    f'{inf.resumen()}\n\n' + '\n'.join(inf.plan + inf.errores + inf.avisos) + '\n')
        if inf.error:
            log.warning('Sincronización: %s', inf.error)
        if not inf.simulacion and not inf.error:
            self.historial.apuntar('sincro', {'copiados': dict(inf.copiados), 'movidos': dict(inf.movidos),
                                              'a_papelera': len(inf.a_papelera), 'conflictos': inf.conflictos,
                                              'errores': inf.errores[:20], 'segundos': round(inf.segundos, 1)})
        if inf.hubo_cambios:
            self.historial.registrar('sincro', ('[Simulación] ' if inf.simulacion else '') + 'Sincronización: ' +
                                     inf.resumen(), inf.pasos, 'simulado' if inf.simulacion else 'hecho')
        if inf.conflictos:
            self.bandeja.notificar('Sincronización', f'{len(inf.conflictos)} archivo(s) cambiado(s) en dos sitios a la vez: '
                                                     'he guardado las dos versiones («… (conflicto fecha)»).')
        for sitio, n in inf.sin_espacio.items():
            self._avisar_una_vez(f'espacio {sitio} {n}', 'Sincronización',
                                 f'{sitio} no tiene espacio: {n} archivo(s) esperan a que liberes sitio.')
        for aviso in inf.avisos + ([f'Cambios dentro de un repo en una copia: no se traen ({len(inf.repos_ignorados)})']
                                   if inf.repos_ignorados else []):
            self._avisar_una_vez(aviso, 'Sincronización', aviso)
        self.sincro_retenidos = inf.retenidos
        clave_ret = tuple(sorted(r for r, _ in inf.retenidos))
        if inf.retenidos and clave_ret != self._retenidos_vistos:
            self._retenidos_vistos = clave_ret
            self.en_ui(self.abrir_borrados)
        self.en_ui(self.bandeja.actualizar)

    def _avisar_una_vez(self, k: str, titulo: str, texto: str) -> None:
        if k not in self._avisos_vistos:
            self._avisos_vistos.add(k)
            self.bandeja.notificar(titulo, texto)

    # ── Trabajo en segundo plano ────────────────────────────────────────────
    def _puede_trabajar(self) -> bool:
        return (not self._parar.is_set() and not self.pausado() and not sistema.pantalla_completa()
                and not sistema.bateria_baja()
                and sistema.segundos_inactivo() >= self.cfg.minutos_inactivo * 60)

    def _hilo_indice(self) -> None:
        sistema.hilo_en_segundo_plano()
        if not os.path.exists(self.cfg.aprendido):
            n = aprendizaje.crear_inicial(self.cfg.aprendido, self.cfg.onedrive, self.cfg.carpetas_indice,
                                          self.cfg.ruta_uni, self.cfg.webs_genericas,
                                          self.cfg.solo_huella + self.cfg.excluir)
            log.info('aprendido.txt creado con %d reglas', n)
        ultimo_escaneo = ultima_limpieza = 0.0
        while not self._parar.is_set():
            if time.time() - ultima_limpieza > 3600 and not self.pausado():
                try:
                    self._limpiar()
                except Exception:
                    log.exception('Falló la limpieza')
                ultima_limpieza = time.time()
            if time.time() - ultimo_escaneo > 1800 and not self.pausado():
                try:
                    cambios = self.indice.escanear()
                    log.info('Índice: %d nuevos, %d cambiados, %d borrados', *cambios)
                    if any(cambios) or not self.perfil.listo:
                        self.perfil.construir(self.indice.filas_perfil())
                except Exception:
                    log.exception('Falló el escaneo del índice')
                ultimo_escaneo = time.time()
                self.en_ui(self.bandeja.actualizar)
            if self._puede_trabajar():
                n = self.indice.trabajar(self._puede_trabajar)
                if n:
                    log.info('Índice: %d archivos procesados', n)
                    self.perfil.construir(self.indice.filas_perfil())
                    self.en_ui(self.bandeja.actualizar)
            self.historial.podar()
            self._parar.wait(30)

    # ── Arranque y salida ───────────────────────────────────────────────────
    def correr(self) -> None:
        log.info('Arranca el Organizador%s', ' (SIMULACIÓN)' if self.cfg.simulacion else '')
        if self.indice.progreso()[1]:
            self.perfil.construir(self.indice.filas_perfil())
        self.bandeja.arrancar()
        self.vigilante.arrancar()
        self._revisar_descargas()
        threading.Thread(target=self._hilo_indice, name='indice', daemon=True).start()
        threading.Thread(target=self._hilo_sincro, name='sincro', daemon=True).start()
        self.root.after(200, self._bucle_ui)
        self.root.after(1500, self.bandeja.actualizar)
        self.root.mainloop()

    def salir(self) -> None:
        log.info('Salida')
        self._parar.set()
        self._sincro_ya.set()
        self.vigilante.parar()
        self.bandeja.parar()
        self.root.quit()


def configurar_registro(cfg) -> None:
    h = logging.handlers.RotatingFileHandler(os.path.join(cfg.datos, 'registro.log'), maxBytes=1 << 20,
                                             backupCount=3, encoding='utf-8')
    h.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s'))
    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    raiz.addHandler(h)
    def excepcion(t, v, tb):
        log.error('Error: %s', ''.join(traceback.format_exception(t, v, tb)))
        if sys.stderr:                       # con consola, que se vea también (con pythonw no hay)
            sys.__excepthook__(t, v, tb)
    sys.excepthook = excepcion
    threading.excepthook = lambda a: log.error('Error en hilo %s: %s', a.thread.name,
                                               ''.join(traceback.format_exception(a.exc_type, a.exc_value,
                                                                                  a.exc_traceback)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--config')
    args = ap.parse_args()
    cfg = config.cargar(args.config)
    import hashlib
    unica = sistema.InstanciaUnica('Local\\OrganizadorPC-' +
                                   hashlib.md5(os.path.normcase(cfg.datos).encode()).hexdigest()[:12])
    if unica.ya_abierto:
        return
    configurar_registro(cfg)
    App(cfg).correr()
