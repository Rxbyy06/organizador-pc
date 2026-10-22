# Organizador del PC: traspaso técnico

> Para quien tenga que entender, ajustar o ampliar el programa (otra conversación con Claude incluida).
> El manual de uso es [LEEME.md](../LEEME.md). Estado al 22-10-2026: **terminado y en uso a diario**.

## 1. Qué es

Un único programa en Python que arranca con Windows y vive como un icono junto al reloj (bandeja). Hace cinco cosas:

| Parte | Qué hace | Archivos principales |
|---|---|---|
| Organizador de Descargas | Cuando termina una descarga, abre una ventanita con la carpeta y el nombre sugeridos; mueve solo con el clic del usuario | `vigilante.py`, `sugeridor.py`, `ventanas.py`, `acciones.py` |
| Limpieza y revisión semanal | Lo que lleva 7 días en Descargas va a la Papelera (con aviso el día antes). Los lunes, ventana con «Resumen» de la semana y «Capturas» (capturas y grabaciones de más de 7 días: Borrar / Guardar en… / Dejar) | `limpieza.py`, `revision.py`, `resumen.py`, `ventanas_revision.py` |
| Sincronizador | Estrella con OneDrive en el centro: OneDrive ↔ G: (solo la uni) y OneDrive ↔ H: (todas las carpetas principales). Al arrancar y cada hora | `sincro.py`, `ventanas_sincro.py` |
| Copias Word de los Google Docs | Un Apps Script en cada cuenta exporta los Docs a .docx; el PC coloca cada Word junto a su Doc en OneDrive (solo lectura) y nunca lo sube a la cuenta de origen | `apps_script/exportar_docs.gs`, `docs_word.py` |
| Avisos y copia | Aviso de espacio, resumen semanal y copia semanal de los datos en OneDrive | `espacio.py`, `resumen.py`, `copia.py` |

## 2. Principios de diseño

- **Nunca borrar definitivamente**: todo va a la Papelera de Windows o a la papelera de Drive. Toda acción importante tiene simulación, ejecución y deshacer.
- **Nada se mueve sin un clic del usuario** (salvo la limpieza de Descargas, que avisa el día antes).
- **El programa nunca pide ni guarda contraseñas**, y no automatiza los sistemas de la universidad (Aula Global): solo lee de qué web viene una descarga.
- **Lo dudoso lo decide el usuario**, con pocas decisiones y bien hechas: nada de pedirle que clasifique tipos de archivo.
- **Carpetas protegidas**: las de `excluir` no se tocan nunca; las de `solo_huella` (privadas) solo se sincronizan y se les calcula la huella, sin abrirlas ni mostrar sus nombres.
- **Que funcione solo**: lo ajustable está en archivos de texto (`config.toml`, `aprendido.txt`).

## 3. Dónde está cada cosa

| Qué | Dónde |
|---|---|
| Programa | `C:\Users\<usuario>\OrganizadorPC` (no está dentro de OneDrive a propósito: SQLite abierto y el programa se vigilaría a sí mismo) |
| Código | Este repositorio (rama `main`) |
| Configuración editable | `config.toml`, creado a partir de `config.example.toml` (rutas, días, umbrales, copias del sincronizador…), con comentarios |
| Lo aprendido (editable) | `aprendido.txt`: `curso N`, `contexto N`, `actividad N` (Aula Global) y `web dominio` → carpeta |
| Datos (no van a git) | `datos\`: `indice.sqlite` (huellas y palabras), `historial.sqlite` (historial, Descargas, estado, estadísticas, duplicados vistos), `sincro.sqlite` (estado por sitio y base acordada), `docs.sqlite` (Word ↔ Doc, PDF decididos), `registro.log`, `sincro_plan.txt` (última pasada) |
| Copia semanal de los datos | `Organizador AAAA-MM-DD.zip` en la carpeta `[copia]` de `config.toml` (las 4 últimas) |
| Entorno Python | `.venv\` (Python 3.14, dependencias en `requirements.txt`; PyMuPDF fijado en 1.28.2 porque la 2.0 arrastra un modelo de IA de 170 MB) |
| Arranque | Acceso directo «Organizador del PC» en la carpeta Inicio y en el menú Inicio (`instalar.py` / `instalar.py --quitar`) |
| Apps Script | Un proyecto en script.google.com en cada cuenta de Google (en mi caso, la de la universidad y la personal), con el servicio «Drive API»; disparador cada 15 min. Deja `Mi unidad\_exportados_docs\` (un `<id>.docx` por Doc y `manifest.json`) |

Sitios (mi configuración): OneDrive (5 GB) en el centro, G: (Drive de la universidad; solo la carpeta de la uni) y H: (Drive personal; todas las carpetas principales). Las carpetas principales tienen «Mantener siempre en este dispositivo».

## 4. Cómo funciona por dentro

**Arranque** (`organizador.pyw` → `app.main`): mutex de instancia única, registro, `App` con tres hilos además del de las ventanas: el vigilante de Descargas (watchdog), el hilo de índice y limpieza (escaneo cada 30 min, huellas solo con el PC inactivo 5 min, limpieza/espacio/turno semanal cada hora) y el hilo del sincronizador (primera pasada a los 90 s, luego cada hora o con «Sincronizar ahora»). Las ventanas solo se tocan desde el hilo de Tk (`App.en_ui`). Lo pesado va en `App.ejecutar` (hilo aparte) y vuelve a la interfaz al terminar. Los hilos de fondo usan `THREAD_MODE_BACKGROUND` (procesador y disco en prioridad baja) y se pausan con pantalla completa, batería baja o «Pausar».

**Organizador.** `vigilante` espera a que el tamaño se quede quieto (ignora `.crdownload`, `.part`…). `sugeridor` decide la carpeta por este orden: reglas de `aprendido.txt` (lee el flujo `Zone.Identifier` con la web de origen) → parecido TF-IDF del contenido con cada carpeta (`perfil.py`, a partir del índice) → categoría por palabras (tema, examen, seminari…). El nombre sigue unas normas fijas (`2024-25 - Final - Soluciones`, `Tema 03 - …`, `Práctica 2 - …`) con el título del PDF (`contenido.py` arregla los acentos de LaTeX) y el curso del examen sacado del texto o de la fecha de creación del PDF. Avisos: idéntico (índice de huellas), casi idéntico (huella del texto), versión nueva, enunciado/soluciones, PDF definitivo de un Doc. Los ZIP se descomprimen en el destino con nombres NFC. Al aceptar se aprende la carpeta para ese curso, recurso o web.

**Acciones y deshacer** (`acciones.py`). Cada acción es una lista de pasos (`crear_carpeta`, `mover`, `papelera`, `extraer`); si uno falla se deshacen los anteriores. `Deshacer` los recorre al revés; lo que fue a la Papelera se recupera leyendo los `$I` de `$Recycle.Bin` (`papelera.py`; en C: bajo la carpeta del SID, en G:/H: en la raíz).

**Sincronizador** (`sincro.py`, explicado en su cabecera):
1. Escanea cada sitio (tamaño y fecha) y compara con el estado de ese mismo sitio en la última pasada. Solo calcula la huella de lo cambiado (en OneDrive la reutiliza del índice).
2. Decide el objetivo de cada archivo: cambio en un solo sitio → gana; en varios con distinto contenido → conflicto (el más reciente conserva el nombre; el otro queda como `Nombre (conflicto AAAA-MM-DD)`); modificar gana a borrar.
3. Aplica primero en OneDrive y luego en G:/H:. Lo que desaparece y reaparece con la misma huella se mueve, y una carpeta renombrada entera se renombra con una sola operación. La copia va a `…orgsync-tmp` y luego se renombra.
4. Guarda solo las filas que cambian (`_guardar` con diferencias).

**Protecciones del sincronizador:**
- Un sitio ilegible o con una carpeta principal desaparecida se salta entero.
- Freno de borrados: más de 20 archivos (cantidad fija) → para y abre una ventana para «Recuperar» o «Mandar a la papelera en todos».
- Un archivo que pasa a 0 bytes no se propaga.
- La versión de OneDrive que va a ser sustituida desde G:/H: se manda antes a la Papelera.
- Sin espacio en el destino → se deja pendiente.
- Repos git: solo de OneDrive a las copias y tras 10 min sin cambios ni `index.lock`.
- Nada que no quepa en la Papelera se borra: Windows lo eliminaría sin avisar, y en H: el límite es de 1,5 GB.

**Copias Word** (`docs_word.py`): antes de cada pasada lee los `manifest.json`. Doc nuevo, cambiado, renombrado o borrado → el Word se copia, actualiza, mueve o va a la papelera. Un Word editado a mano se aparta como `(editado en Word fecha)`, y si choca con un Word propio se llama `… (Doc).docx`. `Sincronizador.excluir()` impide que el Word vuelva a la cuenta de su Doc. El PDF definitivo (mismo nombre o texto que un Doc) siempre se pregunta; «Borrar el Doc» manda su `.gdoc` a la papelera de G:, y Drive lo pasa a su papelera.

## 5. Decisiones de diseño

- Revisión semanal los **lunes**; en Capturas, «Borrar» marcado de entrada; «Dejar» sigue saliendo cada semana y a las 4 semanas de la primera vez se queda para siempre. Semana sin novedades → solo notificación.
- Avisos de espacio: OneDrive ≥ 90 % de 5 GB (estimado sumando la carpeta); G:/H: ≥ 95 % o < 500 MB libres; como mucho uno al día.
- Duplicados del resumen: sin contar los de dentro de repos; el primer resumen enseña los existentes una vez, luego solo los nuevos.
- El script de Apps Script mira las carpetas principales en las dos cuentas.

## 6. Cosas no obvias

- **No usar `git status` para «solo mirar»** los repos sincronizados: reescribe `.git\index`.
- **Pantalla completa**: `SHQueryUserNotificationState` no basta; también cuenta «la ventana activa ocupa el monitor y no está maximizada» (su barra de tareas se oculta sola, así que una maximizada ocupa lo mismo).
- **Drive** conserva la fecha de modificación al copiar, no guarda el atributo de solo lectura, y lo enviado a `G:\$Recycle.Bin` aparece también en la papelera web.
- Al renombrar un Doc, Google cambia su fecha: el Word se reexporta (en H: se copia de nuevo en vez de moverse).
- **Forzar una pasada desde fuera**: reiniciar el programa (la primera pasada es a los 90 s).
- Al editar archivos de Python desde PowerShell, cuidado con `@(@('a','b'))`: PowerShell lo aplana y `$p[0]` pasa a ser una letra. Mejor un editor.

## 7. Pruebas

| Orden | Qué prueba |
|---|---|
| `.venv\Scripts\python.exe -m unittest discover tests` | 57 pruebas: reglas del organizador, limpieza y revisión (reloj simulado), sincronizador (carpetas locales como OneDrive/G:/H:), copias Word, resumen/espacio/copia. Lo que mandan a la Papelera lo recuperan al acabar |
| `python tests/crear_sandbox.py pruebas` | Crea `pruebas\`, una copia de la estructura real con archivos de relleno (sin las notas privadas) y una config que **nunca** apunta a los G:/H: reales |
| `python tests/prueba_organizador.py pruebas <capturas>` | De punta a punta con ventanas de verdad: descargas, sugerencias, Aceptar/Descartar/Más tarde, ZIP, deshacer (49 comprobaciones) |
| `python tests/prueba_limpieza_revision.py pruebas <capturas>` | Aviso del día 6, Papelera del día 7, ventana semanal, «Guardar en…», deshacer (18) |
| `python tests/prueba_drive.py <carpeta local>` | Contra Google Drive real, en `_prueba_sincro` de G: y H:. Úsese solo con permiso del usuario y luego manda esas carpetas a la papelera |
| `python -m organizador.herramientas sincro` | Una pasada del sincronizador en **simulación** sobre lo real (`--de-verdad` para aplicarla) |
| `python -m organizador.herramientas evaluar` / `indexar` / `aprender` / `sugerir <archivo>` / `sincro-inicial` | Calidad del clasificador, índice completo, regenerar `aprendido.txt`, probar una sugerencia, recrear el estado del sincronizador |

Antes de tocar algo que borre o mueva: prueba unitaria, luego la carpeta de pruebas, luego simulación sobre lo real, y solo entonces de verdad. Tras cambiar el programa: reiniciarlo, hacer commit y `git push`.
