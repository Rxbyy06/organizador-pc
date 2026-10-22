"""Web de origen de una descarga, leída del flujo Zone.Identifier que escribe el navegador."""
import re
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

from .nombres import ruta_larga

AULA_GLOBAL = 'aulaglobal.upf.edu'


@dataclass
class Origen:
    host_url: str = ''
    referrer_url: str = ''
    web: str = ''                 # dominio de la página de donde viene
    curso: str = ''               # id de curso (course/view.php?id=)
    contexto: str = ''            # pluginfile.php/<contexto>/<componente>/…
    componente: str = ''          # course, mod_resource, mod_folder, mod_assign…
    actividad: str = ''           # mod/<tipo>/view.php?id=<actividad>
    nombre_recurso: str = ''      # último trozo de la URL de pluginfile

    @property
    def aula_global(self) -> bool:
        return AULA_GLOBAL in self.web or AULA_GLOBAL in self.host_url

    @property
    def es_entrega(self) -> bool:
        return 'assign' in self.componente or '/mod/assign/' in self.referrer_url

    def claves(self) -> list[tuple[str, str]]:
        """Lo que se puede aprender de esta descarga, de más concreto a menos."""
        c = []
        if self.contexto and self.componente != 'course':
            c.append(('contexto', self.contexto))
        if self.actividad:
            c.append(('actividad', self.actividad))
        if self.curso:
            c.append(('curso', self.curso))
        if self.contexto and self.componente == 'course':
            c.append(('contexto', self.contexto))
        if self.web and not self.aula_global:
            c.append(('web', self.web))
        return c

    def describir(self) -> str:
        if self.aula_global:
            return 'Aula Global'
        return self.web or ''


def _host(url: str) -> str:
    if not url.lower().startswith(('http://', 'https://')):
        return ''
    return (urlparse(url).hostname or '').lower()


def de_texto(texto: str) -> Origen:
    o = Origen()
    for linea in texto.splitlines():
        k, _, v = linea.partition('=')
        if k.strip() == 'HostUrl':
            o.host_url = v.strip()
        elif k.strip() == 'ReferrerUrl':
            o.referrer_url = v.strip()
    o.web = _host(o.referrer_url) or _host(o.host_url)
    urls = o.referrer_url + '\n' + o.host_url
    if AULA_GLOBAL in urls:
        if m := re.search(r'course/view\.php\?id=(\d+)', urls):
            o.curso = m.group(1)
        if m := re.search(r'mod/\w+/view\.php\?id=(\d+)', urls):
            o.actividad = m.group(1)
        if m := re.search(r'pluginfile\.php/(\d+)/(\w+)/[^\s]*', urls):
            o.contexto, o.componente = m.group(1), m.group(2)
            ultimo = m.group(0).split('?')[0].rstrip('/').rsplit('/', 1)[-1]
            o.nombre_recurso = unquote(ultimo)
    return o


def leer(ruta: str) -> Origen:
    try:
        with open(ruta_larga(ruta) + ':Zone.Identifier', 'rb') as f:
            datos = f.read(8192)
    except OSError:
        return Origen()
    for cod in ('utf-8', 'utf-16', 'cp1252'):
        try:
            return de_texto(datos.decode(cod))
        except UnicodeDecodeError:
            continue
    return Origen()
