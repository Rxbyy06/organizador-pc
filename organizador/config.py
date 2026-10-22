"""Lectura de config.toml y rutas del programa."""
import os
import tomllib
from dataclasses import dataclass, field

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIAS = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']


@dataclass
class Config:
    descargas: str
    onedrive: str
    universidad: str                      # carpeta relativa a onedrive
    simulacion: bool = True
    ignorar: list[str] = field(default_factory=list)
    segundos_estable: float = 3
    webs_genericas: set[str] = field(default_factory=set)
    carpetas_indice: list[str] = field(default_factory=list)
    leer_texto_en: list[str] = field(default_factory=list)
    solo_huella: list[str] = field(default_factory=list)
    excluir: list[str] = field(default_factory=list)
    minutos_inactivo: float = 5
    dias_historial: int = 30
    dias_descargas: float = 7
    dias_aviso: float = 1
    notificar: bool = True
    carpetas_capturas: list[str] = field(default_factory=list)
    dias_capturas: float = 7
    dia_revision: int = 0                 # 0 = lunes
    semanas_dejar: float = 4
    sincro_simulacion: bool = True
    sincro_minutos: float = 60
    max_borrados: int = 20
    minutos_repo: float = 10
    copias: list[dict] = field(default_factory=list)   # {'nombre', 'raiz', 'carpetas'}
    cuentas_docs: list[dict] = field(default_factory=list)   # {'copia', 'exportados'}
    cuota_onedrive_gb: float = 5
    aviso_onedrive_pct: float = 90
    aviso_drive_pct: float = 95
    aviso_drive_mb: float = 500
    carpeta_copia: str = ''
    copias_guardar: int = 4
    datos: str = os.path.join(RAIZ, 'datos')
    aprendido: str = os.path.join(RAIZ, 'aprendido.txt')
    archivo: str = ''

    @property
    def ruta_uni(self) -> str:
        return os.path.join(self.onedrive, self.universidad)

    def relativa(self, ruta: str) -> str:
        """Ruta relativa a OneDrive (o la absoluta si está fuera)."""
        try:
            rel = os.path.relpath(ruta, self.onedrive)
        except ValueError:
            return ruta
        return ruta if rel.startswith('..') else rel


def cargar(archivo: str | None = None) -> Config:
    archivo = archivo or os.path.join(RAIZ, 'config.toml')
    with open(archivo, 'rb') as f:
        d = tomllib.loads(f.read().decode('utf-8-sig'))
    base = os.path.dirname(os.path.abspath(archivo))
    r, o, i = d.get('rutas', {}), d.get('organizador', {}), d.get('indice', {})
    cfg = Config(
        descargas=r['descargas'],
        onedrive=r['onedrive'],
        universidad=r.get('universidad', '1 - Universidad UPF'),
        simulacion=bool(o.get('simulacion', True)),
        ignorar=list(o.get('ignorar', [])),
        segundos_estable=float(o.get('segundos_estable', 3)),
        webs_genericas={w.lower() for w in o.get('webs_genericas', [])},
        carpetas_indice=list(i.get('carpetas', [])),
        leer_texto_en=list(i.get('leer_texto_en', [])),
        solo_huella=list(i.get('solo_huella', [])),
        excluir=list(i.get('excluir', [])),
        minutos_inactivo=float(i.get('minutos_inactivo', 5)),
        dias_historial=int(d.get('historial', {}).get('dias', 30)),
        archivo=archivo,
    )
    lim, rev = d.get('limpieza', {}), d.get('revision', {})
    cfg.dias_descargas = float(lim.get('dias_descargas', 7))
    cfg.dias_aviso = float(lim.get('dias_aviso', 1))
    cfg.notificar = bool(lim.get('notificar', True))
    cfg.carpetas_capturas = list(rev.get('carpetas', []))
    cfg.dias_capturas = float(rev.get('dias_minimos', 7))
    cfg.dia_revision = DIAS.index(str(rev.get('dia', 'lunes')).strip().lower().replace('é', 'e').replace('á', 'a'))
    cfg.semanas_dejar = float(rev.get('semanas_dejar', 4))
    s = d.get('sincro', {})
    cfg.sincro_simulacion = bool(s.get('simulacion', True))
    cfg.sincro_minutos = float(s.get('cada_minutos', 60))
    cfg.max_borrados = int(s.get('max_borrados', 20))
    cfg.minutos_repo = float(s.get('minutos_repo_quieto', 10))
    cfg.copias = [{'nombre': c['nombre'], 'raiz': c['raiz'], 'carpetas': list(c['carpetas'])}
                  for c in s.get('copias', [])]
    cfg.cuentas_docs = [{'copia': c['copia'], 'exportados': c['exportados']}
                        for c in d.get('docs', {}).get('cuentas', [])]
    e, c = d.get('espacio', {}), d.get('copia', {})
    cfg.cuota_onedrive_gb = float(e.get('cuota_onedrive_gb', 5))
    cfg.aviso_onedrive_pct = float(e.get('aviso_onedrive_pct', 90))
    cfg.aviso_drive_pct = float(e.get('aviso_drive_pct', 95))
    cfg.aviso_drive_mb = float(e.get('aviso_drive_mb_libres', 500))
    cfg.carpeta_copia = c.get('carpeta', '')
    cfg.copias_guardar = int(c.get('guardar', 4))
    # Una config de pruebas puede llevar sus propios datos y aprendido.txt.
    p = d.get('programa', {})
    if 'datos' in p:
        cfg.datos = os.path.join(base, p['datos'])
    if 'aprendido' in p:
        cfg.aprendido = os.path.join(base, p['aprendido'])
    os.makedirs(cfg.datos, exist_ok=True)
    return cfg
