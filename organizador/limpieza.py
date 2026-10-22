"""Limpieza de Descargas: lo que lleva 7 días va a la Papelera, siempre con un día de aviso antes."""
import logging
import os
import time

from .huellas import ignorado
from .vigilante import TEMPORALES

log = logging.getLogger(__name__)
DIA = 86400


def en_descargas(cfg) -> list[str]:
    """Todo lo de Descargas que cuenta: archivos y carpetas, menos lo ignorado y lo que aún se descarga."""
    try:
        nombres = os.listdir(cfg.descargas)
    except OSError:
        return []
    res = []
    for n in nombres:
        if n in cfg.ignorar or n.startswith('.') or ignorado(n) or n.lower().endswith(TEMPORALES):
            continue
        res.append(os.path.join(cfg.descargas, n))
    return res


class Limpieza:
    def __init__(self, cfg, historial, ejecutor, ahora=time.time):
        self.cfg, self.historial, self.ejecutor, self.ahora = cfg, historial, ejecutor, ahora

    @property
    def limite(self) -> float:
        return self.cfg.dias_descargas * DIA

    @property
    def aviso_desde(self) -> float:
        return max(0.0, self.limite - self.cfg.dias_aviso * DIA)

    def estado(self, ruta: str) -> tuple[float, float]:
        """(primera vez que se vio, segundos que le quedan antes de ir a la Papelera)."""
        info = self.historial.descarga_info(os.path.basename(ruta))
        primera = info[0] if info else self.ahora()
        return primera, primera + self.limite - self.ahora()

    def revisar(self) -> tuple[list[str], list[str]]:
        """Avisa de lo que se irá mañana y manda a la Papelera lo ya avisado. Devuelve (avisados ahora, tirados)."""
        ahora = self.ahora()
        avisar, tirar = [], []
        presentes = en_descargas(self.cfg)
        for ruta in presentes:
            nombre = os.path.basename(ruta)
            info = self.historial.descarga_info(nombre)
            if info is None:                       # p. ej. una carpeta: empieza a contar hoy
                self.historial.descarga_nueva(nombre, cuando=ahora)
                continue
            primera, aviso = info
            edad = ahora - primera
            if edad < self.aviso_desde:
                continue
            if aviso is None:
                self.historial.descarga_avisada(nombre, ahora)
                avisar.append(ruta)
            # Nunca sin haber avisado al menos un día antes (aunque el PC estuviera apagado).
            elif edad >= self.limite and ahora - aviso >= self.cfg.dias_aviso * DIA - 4 * 3600:
                tirar.append(ruta)
        self.historial.descargas_sincronizar([os.path.basename(r) for r in presentes])
        if tirar:
            try:
                self.ejecutor.limpiar_descargas(tirar)
            except Exception:
                log.exception('Falló la limpieza de Descargas')
                tirar = []
        self.historial.poner_estado('ultima_limpieza', ahora)
        return avisar, tirar
