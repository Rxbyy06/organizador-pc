"""Espacio en OneDrive, G: y H:, y cuándo avisar."""
import os
import shutil
from dataclasses import dataclass

GB = 1 << 30


@dataclass
class Uso:
    sitio: str
    usado: float          # bytes
    total: float
    aviso: bool

    @property
    def pct(self) -> float:
        return 100 * self.usado / self.total if self.total else 0

    @property
    def libre(self) -> float:
        return max(0.0, self.total - self.usado)

    def texto(self) -> str:
        return f'{self.sitio} {self.pct:.0f} % lleno ({self.libre / GB:.2f} GB libres)'.replace('.', ',')


def tamano_carpeta(ruta: str) -> int:
    total, pila = 0, [ruta]
    while pila:
        try:
            with os.scandir(pila.pop()) as it:
                for e in it:
                    try:
                        if e.is_dir(follow_symlinks=False):
                            pila.append(e.path)
                        else:
                            total += e.stat(follow_symlinks=False).st_size
                    except OSError:
                        pass
        except OSError:
            pass
    return total


def medir(cfg, disco=shutil.disk_usage, tamano=tamano_carpeta) -> list[Uso]:
    """OneDrive: lo que suma su carpeta frente al plan. G: y H:: lo que dice la unidad (la cuota de la cuenta)."""
    res = []
    if os.path.isdir(cfg.onedrive):
        cuota = cfg.cuota_onedrive_gb * GB
        usado = tamano(cfg.onedrive)
        res.append(Uso('OneDrive', usado, cuota, 100 * usado / cuota >= cfg.aviso_onedrive_pct))
    for c in cfg.copias:
        try:
            u = disco(c['raiz'])
        except OSError:
            continue
        pct = 100 * u.used / u.total if u.total else 0
        res.append(Uso(c['nombre'], u.used, u.total,
                       pct >= cfg.aviso_drive_pct or u.free < cfg.aviso_drive_mb * (1 << 20)))
    return res
