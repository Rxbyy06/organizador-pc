"""Carpeta y nombre sugeridos para una descarga, y avisos de duplicados."""
import os
import re
from dataclasses import dataclass, field

from . import carpetas as C
from . import contenido, zips
from . import origen as O
from .huellas import huella
from .nombres import capitalizar, clave, limpiar_original, nfc, partir_ext, recortar, sanear, sin_tildes
from .perfil import tokenizar


def _n(s: str) -> str:
    return sin_tildes(nfc(s)).lower().replace('_', ' ')


# ── Palabras estables ───────────────────────────────────────────────────────
# (?![a-z]) en vez de \b: «tema4», «seminari3» también cuentan.
EXAM_FUERTE = re.compile(r'\b(examen|examens|examenes|exam|exams|parcial|parcials|parciales|midterm|'
                         r'recuperacio|recuperacion|resit|simulacre|simulacro|extraordinari[ao]?)(?![a-z])')
EXAM_DEBIL = re.compile(r'\b(final|finals|control|test|quiz)(?![a-z])')
SEMINARIO = re.compile(r'\b(seminari|seminaris|seminario|seminarios|seminar|seminars)(?![a-z])|\bsem\s?\d')
PRACTICA = re.compile(r'\b(practica|practiques|practicas|lab|labs|laboratori|laboratorio|laboratory|'
                      r'assignment|projecte|proyecto|project)(?![a-z])|\bp\d{1,2}\b')
EJERCICIOS = re.compile(r'\b(exercicis?|ejercicios?|exercises?|problemes|problemas|problems|llista|'
                        r'lista|hoja|problem set)(?![a-z])')
TEORIA_RX = re.compile(r'\b(tema|temes|teoria|apunts|apuntes|transparencies|diapositives|slides|'
                       r'lecture|unitat|unidad|chapter|capitol)(?![a-z])|\bt\d{1,2}\b')

SOL = re.compile(r'\b(sol|sols|solucio|solucions|solucion|soluciones|solution|solutions|solved|resolt|resolts|'
                 r'resuelto|resueltos|resolucio|resolucion|correccio|correccion|respostes|respuestas|answers)\b')
ENUNC = re.compile(r'\b(enunciat|enunciats|enunciado|enunciados|statement)\b')
ENTREGA = re.compile(r'\b(entrega|lliurament|submission|entregable)\b')

TEMA_N = re.compile(r'\b(?:tema|temes|unitat|unidad|unit|chapter|capitol|capitulo|lecture|leccio|leccion|'
                    r'lesson|t)\s*[-.]?\s*(\d{1,2})(?:\s*(?:-|a|i|y|&|and)\s*(\d{1,2}))?\b')
SEM_N = re.compile(r'\b(?:seminari|seminario|seminar|sem)\s*[-.]?\s*(\d{1,2})\b')
PRAC_N = re.compile(r'\b(?:practica|practiques|practicas|lab|laboratori|laboratorio|p)\s*[-.]?\s*(\d{1,2})\b')
SES_N = re.compile(r'\b(?:sessio|sesion|session)\s*[-.]?\s*(\d{1,2})\b')
CLASE = re.compile(r'\b(classe|clase|class)\b')
FECHA = re.compile(r'\b(20\d\d)[-./](\d{1,2})[-./](\d{1,2})\b|\b(\d{1,2})[-./](\d{1,2})[-./](20\d\d)\b')
CURSO = re.compile(r'\b(20\d\d)\s*[-/]\s*(?:20)?(\d\d)\b')
MESES = {'gener': 1, 'enero': 1, 'january': 1, 'febrer': 2, 'febrero': 2, 'february': 2, 'marc': 3,
         'marzo': 3, 'march': 3, 'abril': 4, 'april': 4, 'maig': 5, 'mayo': 5, 'may': 5, 'juny': 6,
         'junio': 6, 'june': 6, 'juliol': 7, 'julio': 7, 'july': 7, 'setembre': 9, 'septiembre': 9,
         'september': 9, 'octubre': 10, 'october': 10, 'novembre': 11, 'noviembre': 11, 'november': 11,
         'desembre': 12, 'diciembre': 12, 'december': 12}
MES_ANO = re.compile(r'\b(' + '|'.join(MESES) + r')\w*\s*(?:de |del |d\')?\s*(20\d\d)\b')
ANO = re.compile(r'\b(20[012]\d)\b')
IDIOMA_FINAL = re.compile(r'[\s-]+(ca|cat|es|esp|en|eng)$', re.I)
PREFIJO_TITULO = re.compile(
    r'^\s*(tema|temes|unitat|unidad|unit|chapter|cap[ií]tol|cap[ií]tulo|lecture|seminari|seminario|seminar|'
    r'pr[àáa]ctica|practice|practical|lab|laboratori|laboratorio|sessi[óo]|sesi[óo]n|session|exercise|'
    r'exercici|ejercicio|t(?=\s?\d))\s*\d{1,2}(\s*[-–a]\s*\d{1,2})?\b\s*[-–:.)]*\s*', re.I)
# Palabras que solas no son un título.
GENERICOS = {'physics', 'fisica', 'matematiques', 'matematicas', 'mathematics', 'calculus', 'calcul', 'calculo',
             'algebra', 'lineal', 'linear', 'tema', 'lab', 'session', 'practice', 'seminar', 'unit',
             'introduccion', 'introduccio', 'introduction', 'presentacio', 'presentacion', 'presentation',
             'index', 'indice', 'contents', 'continguts', 'resum', 'summary', 'grup', 'grupo', 'group'}
QUITAR_TITULO = re.compile(r'\b(solucions|soluciones|solutions|enunciat|enunciado|amb solucions|'
                           r'con soluciones)\b', re.I)


@dataclass
class Aviso:
    tipo: str        # identico, casi, version, enunciado_sobra, soluciones_existen, carpeta_existe
    texto: str
    ruta: str = ''
    opcion: str = ''               # texto de la casilla, si la hay
    marcado: bool = True
    permite_descartar: bool = False


@dataclass
class Sugerencia:
    archivo: str
    carpeta: str
    nombre: str
    ext: str
    motivo: str
    seguro: bool
    origen: O.Origen
    contenido: contenido.Contenido
    hash: str
    tam: int
    zip: zips.InfoZip | None = None
    senales: dict = field(default_factory=dict)
    duplicados: list[Aviso] | None = None

    @property
    def es_zip(self) -> bool:
        return self.zip is not None and not self.zip.error


# ── Deducciones ─────────────────────────────────────────────────────────────
def deducir_categoria(t_nombre: str, t_lineas: str, o: O.Origen, z: zips.InfoZip | None) -> str | None:
    for texto, fuerte in ((_n(t_nombre), True), (_n(t_lineas), False)):
        if EXAM_FUERTE.search(texto):
            return C.EXAMENES
        if SEMINARIO.search(texto):
            return C.SEMINARIOS
        if PRACTICA.search(texto):
            return C.PRACTICAS
        if fuerte and EXAM_DEBIL.search(texto):
            return C.EXAMENES
        if EJERCICIOS.search(texto):
            return C.EJERCICIOS
        if TEORIA_RX.search(texto):
            return C.TEORIA
    if (z and z.tiene_codigo) or o.es_entrega:
        return C.PRACTICAS
    return None


def curso_academico(textos: list[str], trimestre: int | None = None, recuperacion: bool = False,
                    creado: tuple[int, int] | None = None) -> str | None:
    """«2024-25» a partir de lo que diga el documento: curso, mes y año, fecha o, en último caso, el año."""
    def curso(ano, mes):
        if not 1 <= mes <= 12:
            return None
        inicio = ano if mes >= 9 else ano - 1
        return f'{inicio}-{(inicio + 1) % 100:02d}'

    textos = [_n(t) for t in textos if t]
    for t in textos:
        for m in CURSO.finditer(t):
            a, b = int(m.group(1)), int(m.group(2))
            if b == (a + 1) % 100:
                return f'{a}-{b:02d}'
        if m := MES_ANO.search(t):
            return curso(int(m.group(2)), MESES[m.group(1)])
        if m := FECHA.search(t):
            return curso(int(m.group(1)), int(m.group(2))) if m.group(1) else curso(int(m.group(6)), int(m.group(5)))
    ano = next((int(m.group(1)) for t in textos if (m := ANO.search(t))), None)
    if creado and (ano is None or creado[0] == ano):
        return curso(*creado)            # el PDF se hizo ese mes: casi siempre, el del examen
    if ano:
        # Solo el año: los exámenes del T1 (salvo la recuperación de julio) son de oct.-dic.
        return curso(ano, 11 if trimestre == 1 and not recuperacion else 6)
    return None


def _tipo_examen(t: str) -> str:
    if re.search(r'\b(recuperacio|recuperacion|resit|extraordinari[ao]?)\b', t):
        return 'Recuperación'
    if re.search(r'\b(parcial|parcials|parciales|midterm)\b', t):
        n = re.search(r'\b(?:parcial|midterm)\s*(\d)\b|\b(\d)\s*(?:r|er|o|º|n)?\s*parcial', t)
        if not n and re.search(r'\b(primer|first)\s+parcial', t):
            return 'Parcial 1'
        if not n and re.search(r'\b(segon|segundo|second)\s+parcial', t):
            return 'Parcial 2'
        return f'Parcial {n.group(1) or n.group(2)}' if n else 'Parcial'
    if re.search(r'\bcontrol\b', t):
        return 'Control'
    if re.search(r'\b(test|quiz)\b', t):
        return 'Test'
    if re.search(r'\b(simulacre|simulacro|mock)\b', t):
        return 'Simulacro'
    return 'Final'


def limpiar_titulo(titulo: str, asignatura: str = '', evitar: set[str] = frozenset()) -> str:
    """Quita del título lo que ya dice el nombre: «Tema 3:», la asignatura, códigos, «Soluciones»…

    «evitar» son las palabras que salen en casi todo lo de la asignatura (su nombre en inglés,
    por ejemplo): un trozo hecho solo de ellas no es un título.
    """
    de_asignatura = set(tokenizar(asignatura)) | GENERICOS | evitar
    t = nfc(titulo).replace('​', '')
    t = re.sub(r'\(?\b(last update|[úu]ltima actualizaci[óo]n|darrera actualitzaci[óo]).*$', '', t, flags=re.I)
    t = re.sub(r'\b20\d\d\s*[-/]\s*(20)?\d\d\b', '', t)                # «2024-25»
    partes = re.split(r'(\s+[—–|]\s+|:\s+|\s+-\s+|\.\s+)', t)
    res = ''
    for i in range(0, len(partes), 2):
        trozo = re.sub(r'^\(\w{1,5}\)\s*', '', partes[i].strip())       # «(B1) …»
        trozo = PREFIJO_TITULO.sub('', trozo)
        trozo = QUITAR_TITULO.sub('', trozo)
        trozo = re.sub(r'\s*\(\d[\d/ ,]*\)', '', trozo)                  # «(27057/27188)»
        trozo = re.sub(r'\b(continguts|contenidos|contents|[ií]ndex|[ií]ndice|outline)\s*$', '', trozo, flags=re.I)
        if trozo.count('(') != trozo.count(')'):
            trozo = trozo.replace('(', '').replace(')', '')
        # «Calculus I Derivada…»: fuera el nombre de la asignatura con su número romano del principio.
        w = trozo.split()
        for j in range(1, min(4, len(w) - 1)):
            if re.fullmatch(r'(?i)i{1,3}|iv', w[j]):
                if all(sin_tildes(x).lower().strip('.,') in de_asignatura for x in w[:j]):
                    trozo = ' '.join(w[j + 1:])
                break
        trozo = IDIOMA_FINAL.sub('', trozo).strip(' -–:.,;')
        palabras = set(tokenizar(trozo))
        if trozo and palabras and not palabras <= de_asignatura:
            sep = partes[i - 1] if i and res else ''
            res += ('. ' if sep.strip() == '.' else ' - ' if sep else '') + trozo
    t = re.sub(r'\s+', ' ', res).strip(' -–:.,;')
    if len(t) > 70:
        t = t[:70].rsplit(' ', 1)[0].rstrip(' -–:.,;')
    return capitalizar(t) if t else ''


def elegir_titulo(s: dict, asignatura: str = '') -> str:
    """El primer candidato que dice algo: ni vacío ni solo el nombre de la asignatura."""
    for cand in s['titulos'] + [s['recurso'], s['limpio']]:
        if t := limpiar_titulo(cand, asignatura, s.get('evitar', set())):
            return t
    return ''


def _ancho(palabra: str, n: int, hermanos: list[str]) -> str:
    """Ceros a la izquierda solo si la serie llega a 10."""
    dos = n >= 10 or any(
        (m := re.match(rf'{palabra} (\d+)', h)) and (len(m.group(1)) == 2 or int(m.group(1)) >= 10)
        for h in hermanos)
    return f'{n:02d}' if dos else str(n)


def componer_nombre(categoria: str | None, s: dict, hermanos: list[str], asignatura: str = '',
                    trimestre: int | None = None) -> str:
    """Nombre según las normas del apartado 1 del traspaso (sin extensión)."""
    t = _n(f"{s['limpio']} {s['recurso']} {' '.join(s['titulos'])}")
    t_lineas = _n(' '.join(s['lineas'][:3]))
    titulo = elegir_titulo(s, asignatura)
    sol = bool(SOL.search(t) or SOL.search(t_lineas))
    tipo_doc = 'Soluciones' if sol else 'Entrega' if ENTREGA.search(t) else 'Enunciado' if ENUNC.search(t) else ''

    def unir(*partes):
        return ' - '.join(p for p in partes if p)

    if categoria == C.EXAMENES:
        tipo = _tipo_examen(t)
        ano = curso_academico([f"{s['limpio']} {s['recurso']} {' '.join(s['titulos'])}", ' '.join(s['lineas'][:8])],
                              trimestre, tipo == 'Recuperación', s.get('creado'))
        return unir(ano, tipo, 'Soluciones' if sol else '')
    if categoria == C.SEMINARIOS and (m := SEM_N.search(t)):
        return unir(f"Seminario {_ancho('Seminario', int(m.group(1)), hermanos)}", titulo, tipo_doc)
    if categoria == C.PRACTICAS and (m := PRAC_N.search(t)):
        return unir(f"Práctica {_ancho('Práctica', int(m.group(1)), hermanos)}", titulo, tipo_doc)
    if re.search(r'\b(sessio|sesion|session)\b', t) and (m := FECHA.search(t)):
        a, mes, d = (m.group(1), m.group(2), m.group(3)) if m.group(1) else (m.group(6), m.group(5), m.group(4))
        return unir(f'Sesión {a}-{int(mes):02d}-{int(d):02d}', titulo)
    if m := SES_N.search(t):
        return unir(f"Sesión {_ancho('Sesión', int(m.group(1)), hermanos)}", titulo)
    if CLASE.search(t) and (m := FECHA.search(t)):
        a, mes, d = (m.group(1), m.group(2), m.group(3)) if m.group(1) else (m.group(6), m.group(5), m.group(4))
        return f'Clase {a}-{int(mes):02d}-{int(d):02d}'
    if categoria in (C.TEORIA, None) and (m := TEMA_N.search(t)):
        a = int(m.group(1))
        b = int(m.group(2)) if m.group(2) and int(m.group(2)) > a else None
        num = _ancho('Tema', max(a, b or 0), hermanos)
        ancho = len(num) if max(a, b or 0) < 10 else 2
        tema = f'Tema {a:0{ancho}d}' + (f'-{b:0{ancho}d}' if b else '')
        return unir(tema, titulo)
    nombre = titulo or capitalizar(s['limpio'])
    if sol and categoria == C.EJERCICIOS and 'soluciones' not in _n(nombre):
        nombre = unir(nombre, 'Soluciones')
    return nombre


class Sugeridor:
    UMBRAL = 0.03

    def __init__(self, cfg, aprendido, indice, perfil):
        self.cfg, self.aprendido, self.indice, self.perfil = cfg, aprendido, indice, perfil
        self.words = None                     # copias Word de los Docs, para el aviso de PDF definitivo

    def sugerir(self, archivo: str) -> Sugerencia:
        base, ext = partir_ext(os.path.basename(archivo))
        o = O.leer(archivo)
        z = zips.analizar(archivo) if ext == '.zip' else None
        c = contenido.Contenido() if z else contenido.analizar(archivo)
        s = {'limpio': limpiar_original(base),
             'recurso': limpiar_original(partir_ext(o.nombre_recurso)[0]) if o.nombre_recurso else '',
             'titulos': c.titulos, 'lineas': c.lineas, 'creado': c.creado,
             'zip': ' '.join(rel for _, rel in z.miembros[:200]) if z else ''}
        tokens = tokenizar(f"{s['limpio']} {s['recurso']} {' '.join(c.titulos)} {c.texto[:6000]} {s['zip']}")
        carpeta, motivo, seguro = self._donde(o, tokens)

        asig = C.asignatura_de(carpeta, self.cfg.ruta_uni)
        if asig and os.path.normcase(carpeta) in (os.path.normcase(asig.ruta), os.path.normcase(asig.base())):
            cat = deducir_categoria(f"{s['limpio']} {s['recurso']} {c.titulo}", ' '.join(c.lineas[:6]), o, z) \
                or self.perfil.categoria(os.path.relpath(asig.ruta, self.cfg.onedrive), tokens) \
                or (C.TEORIA if ext == '.pdf' else C.OTROS)
            carpeta = asig.categoria(cat)
        sug = Sugerencia(archivo, carpeta, '', ext, motivo, seguro, o, c, huella(archivo),
                         os.path.getsize(archivo), z, s)
        sug.nombre = self.nombre_para(sug, carpeta)
        return sug

    def _donde(self, o: O.Origen, tokens: list[str]) -> tuple[str, str, bool]:
        textos = {'curso': 'curso {} de Aula Global, ya aprendido',
                  'contexto': 'este recurso de Aula Global ya lo conocía',
                  'actividad': 'esta actividad de Aula Global ya la conocía',
                  'web': 'lo que bajas de {} va aquí (aprendido)'}
        for (tipo, valor), destino in self.aprendido.buscar(o.claves()):
            ruta = os.path.join(self.cfg.onedrive, destino)
            if os.path.isdir(ruta) or os.path.isdir(os.path.dirname(ruta)):
                return ruta, textos[tipo].format(valor), True
        ranking = self.perfil.clasificar(tokens) if self.perfil.listo else []
        if o.aula_global:     # casi todo lo de Aula Global es de la uni (pero no todo: el inglés C1 también)
            uni = self.cfg.universidad + os.sep
            ranking = sorted(((c, p * (1.3 if c.startswith(uni) else 1)) for c, p in ranking), key=lambda x: -x[1])
        if ranking and ranking[0][1] >= self.UMBRAL:
            clase, p = ranking[0]
            segundo = ranking[1][1] if len(ranking) > 1 else 0
            seguro = p >= 0.12 and p >= segundo * 1.25
            if o.aula_global and o.curso:
                motivo = f'curso nuevo de Aula Global ({o.curso}): comprueba la asignatura y lo recordaré'
                seguro = False
            else:
                motivo = 'se parece a lo que ya tienes aquí' + ('' if seguro else '; no estoy seguro, revísalo')
            return os.path.join(self.cfg.onedrive, clase), motivo + self._web_nueva(o), seguro
        raiz = self.cfg.ruta_uni if o.aula_global else self.cfg.onedrive
        return raiz, 'no sé dónde va: elígelo con «Cambiar…»' + self._web_nueva(o), False

    def _web_nueva(self, o: O.Origen) -> str:
        if o.web and not o.aula_global and o.web not in self.cfg.webs_genericas:
            return f' · web nueva ({o.web}): recordaré dónde lo guardas'
        return ''

    def nombre_para(self, s: Sugerencia, carpeta: str) -> str:
        """Nombre sugerido para esa carpeta (cambia con la categoría y con los hermanos)."""
        if s.es_zip:
            z = s.zip
            if z.archivo_unico:
                base = partir_ext(os.path.basename(z.miembros[0][1]))[0]
            else:
                base = z.raiz_unica or s.senales['limpio']
            return recortar(carpeta, sanear(base), '')
        asig = C.asignatura_de(carpeta, self.cfg.ruta_uni)
        categoria = None
        if asig:
            nombres_cat = {C._sin_numero(x): x for x in C.CATEGORIAS}
            for parte in os.path.relpath(carpeta, asig.ruta).split(os.sep):
                categoria = nombres_cat.get(C._sin_numero(parte), categoria)
        try:
            hermanos = [nfc(h) for h in os.listdir(carpeta)]
        except OSError:
            hermanos = []
        if asig:
            senales = dict(s.senales, evitar=self.perfil.tipicas(os.path.relpath(asig.ruta, self.cfg.onedrive)))
            nombre = componer_nombre(categoria, senales, hermanos, asig.nombre, asig.trimestre)
        else:
            nombre = elegir_titulo(s.senales)
        return recortar(carpeta, sanear(nombre), s.ext)

    def ext_final(self, s: Sugerencia, descomprimir: bool) -> str:
        if s.es_zip and descomprimir:
            return os.path.splitext(s.zip.miembros[0][1])[1].lower() if s.zip.archivo_unico else ''
        return s.ext

    def duplicados(self, s: Sugerencia) -> list[Aviso]:
        """Idénticos y casi idénticos en todo el índice (no depende de la carpeta elegida)."""
        rel = lambda r: self.cfg.relativa(os.path.dirname(r))
        iguales = [r for r in self.indice.iguales(s.hash, s.tam)
                   if os.path.normcase(r) != os.path.normcase(s.archivo)]
        if iguales:
            return [Aviso('identico', f'Ya tienes este archivo, idéntico, en {rel(iguales[0])}: '
                                      f'«{os.path.basename(iguales[0])}».', iguales[0], permite_descartar=True)]
        if casi := self.indice.mismo_texto(s.contenido.texto_hash, s.hash):
            return [Aviso('casi', f'DUDOSO: parece el mismo PDF que «{os.path.basename(casi[0])}» '
                                  f'({rel(casi[0])}): mismo texto, archivo distinto. Decide tú.',
                          casi[0], permite_descartar=True)]
        return []

    def junto_al_duplicado(self, s: Sugerencia) -> None:
        """Si ya lo tiene idéntico, lo lógico es la misma carpeta y el mismo nombre (y casi seguro, Descartar)."""
        for a in s.duplicados or []:
            if a.tipo == 'identico' and not s.es_zip:
                s.carpeta = os.path.dirname(a.ruta)
                s.nombre = partir_ext(os.path.basename(a.ruta))[0]
                s.motivo, s.seguro = 'ahí está la copia idéntica que ya tienes', True
                return

    def avisos(self, s: Sugerencia, carpeta: str, nombre: str, descomprimir: bool) -> list[Aviso]:
        if s.duplicados is None:
            s.duplicados = self.duplicados(s)
        av = list(s.duplicados)
        iguales = [a.ruta for a in av if a.tipo == 'identico']
        ext = self.ext_final(s, descomprimir)
        if s.es_zip and descomprimir and not s.zip.archivo_unico:
            if os.path.isdir(os.path.join(carpeta, nombre)):
                av.append(Aviso('carpeta_existe', f'Ya existe la carpeta «{nombre}»: se añadirán dentro los '
                                                  'archivos que falten (los idénticos se saltan).'))
            return av
        destino = os.path.join(carpeta, nombre + ext)
        if os.path.exists(destino) and os.path.normcase(destino) not in map(os.path.normcase, iguales):
            av.append(Aviso('version', f'Ya hay un «{nombre}{ext}» distinto en esa carpeta: '
                                       'parece una versión nueva.', destino,
                            opcion='Sustituir la antigua (va a la Papelera)'))
        try:
            hermanos = {clave(h): h for h in os.listdir(carpeta)}
        except OSError:
            hermanos = {}
        if m := re.search(r'\s-\sSoluciones\b', nombre):
            enunciado = nombre[:m.start()] + nombre[m.end():]
            for k in (clave(enunciado + ext), clave(enunciado + ' - Enunciado' + ext)):
                if k in hermanos:
                    av.append(Aviso('enunciado_sobra', f'Tienes el enunciado «{hermanos[k]}»; con las soluciones '
                                                       'ya no hace falta.', os.path.join(carpeta, hermanos[k]),
                                    opcion='Mandar el enunciado a la Papelera'))
        else:
            base = clave(re.sub(r'\s-\sEnunciado\b', '', nombre))
            for k, h in hermanos.items():
                if k.startswith(base + ' - soluciones') and k.endswith(clave(ext)):
                    av.append(Aviso('soluciones_existen', f'Ya tienes la versión con soluciones: «{h}». '
                                                          'Mejor quedarse solo con esa.',
                                    os.path.join(carpeta, h), permite_descartar=True))
                    break
        # ¿Es la versión definitiva de un Google Doc de esa carpeta? Se pregunta; nunca se decide solo.
        if ext == '.pdf' and self.words is not None:
            rel_carpeta = clave(self.cfg.relativa(carpeta))
            for id_, _copia, nombre_doc, _ruta, rel, _exp, _h in self.words.filas():
                if clave(os.path.dirname(rel)) == rel_carpeta and clave(nombre_doc) == clave(nombre):
                    av.append(Aviso('pdf_definitivo', f'Este PDF parece la versión definitiva de «{nombre_doc}» '
                                                      '(Google Doc). ¿Borro el Doc editable o lo conservas?', id_,
                                    opcion='Mandar el Doc editable a la papelera (y su Word)', marcado=False))
        return av
