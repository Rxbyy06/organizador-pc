# Organizador del PC

Ordena lo que descargas, limpia Descargas y las capturas viejas, mantiene iguales OneDrive, G: y H:, y guarda copias en Word de tus Google Docs. Funciona solo desde el icono junto al reloj. Este archivo explica cómo usarlo; los detalles técnicos están en [docs/TRASPASO.md](docs/TRASPASO.md).

## Qué hace

### Organizador de Descargas

- **Vigila Descargas.** Cuando una descarga termina, sale una ventanita abajo a la derecha con todo medio hecho:
  - la carpeta sugerida, con «Cambiar…», que abre el selector de carpetas de Windows (el del Explorador: doble clic para entrar, barra de direcciones, búsqueda y «Nueva carpeta»);
  - el nombre sugerido, editable;
  - los avisos: duplicados, versión nueva, enunciado/soluciones.
- **Botones:**
  - **Aceptar** (o Enter) mueve el archivo con ese nombre a esa carpeta.
  - **Elegir carpeta…** sale en lugar de Aceptar cuando el programa no sabe dónde va: así nada acaba en la raíz de OneDrive sin querer.
  - **Más tarde** (o Esc, o cerrar la ventanita) lo deja en Descargas, en la lista de Pendientes.
  - **Descartar** solo sale si es un duplicado, y lo manda a la Papelera.
- **Si aceptas guardarlo donde ya está idéntico,** no se crea un «… (2)»: la descarga va a la Papelera y queda anotado en el Historial.
- **ZIP:** propone descomprimirlo directamente en el destino y mandar el zip a la Papelera.
- **Nunca mueve nada sin tu clic y nunca borra nada definitivamente.** Lo que quita va a la Papelera de reciclaje.
- **Si estás a pantalla completa** (un juego, una película), la ventanita espera a que salgas.
- **El trabajo pesado** (calcular las huellas para encontrar duplicados) solo se hace con el PC inactivo 5 minutos, en prioridad baja de procesador y de disco. Se para si juegas o si la batería está baja.

### Limpieza de Descargas

- **Lo que lleva 7 días en Descargas** (contados desde que llegó) va a la Papelera de reciclaje. Entra todo: archivos, instaladores y carpetas sueltas.
- **Un día antes avisa:** en Pendientes sale en naranja («a la Papelera mañana») y salta una notificación de Windows.
- **Nunca tira nada sin ese aviso.** Si el PC estuvo apagado, primero avisa y lo tira al día siguiente.
- **En el Historial** cada limpieza tiene su **Deshacer**, que lo devuelve todo a Descargas.
- **Para salvar algo,** organízalo con «Organizar» o muévelo tú.

### Revisión semanal (los lunes): resumen y capturas

El lunes (o en el siguiente arranque, si el PC estaba apagado) se abre una ventana con dos pestañas.

- **Resumen** de la semana:
  - la sincronización (qué se copió, movió o fue a la papelera en cada sitio);
  - los **conflictos**, con su ruta entera (doble clic: abrir su carpeta);
  - las copias Word, lo que hizo el organizador y el espacio de OneDrive, G: y H:;
  - lo pendiente;
  - los **duplicados nuevos** (los de dentro de repos de código no cuentan). Marca la copia que sobra y pulsa «A la papelera» (siempre deja al menos una); cada grupo tiene también «No volver a avisar».
- **Capturas:** la revisión de capturas que se explica justo debajo.

Si la semana no tiene nada destacable, no se abre ninguna ventana: solo sale el aviso «Semana sin novedades».

### Aviso de espacio

- **OneDrive:** avisa al pasar del 90 % de 5 GB. Lo calcula sumando lo que hay en su carpeta, así que es una estimación: la papelera online también ocupa.
- **G: y H::** avisan al pasar del 95 % o al quedar menos de 500 MB libres.
- **Cómo avisa:** con una notificación, como mucho una vez al día, y en la línea de estado del icono.

### Copia semanal de tus datos

Cada lunes se guarda una copia, `Organizador AAAA-MM-DD.zip`, en la carpeta `[copia]` de `config.toml`, y la sincronización la lleva también a H:. Se guardan las 4 últimas.

Contiene `aprendido.txt`, `config.toml` y los datos del programa: el índice, el historial y el estado de la sincronización y de las copias Word.

### Revisión semanal de capturas

- **Qué revisa:** las capturas y grabaciones de pantalla de más de 7 días, de `OneDrive\Imágenes\Capturas de pantalla` y `Videos\Captures`.
- **Cuándo:** la ventana se abre sola el lunes. Si ese día el PC está apagado, sale en el siguiente arranque, y espera si estás a pantalla completa.
- **Cada captura** tiene tres opciones:
  - **Borrar:** viene marcada de entrada y la manda a la Papelera.
  - **Guardar en…:** carpeta y nombre, como con las descargas.
  - **Dejar:** se queda donde está.
- **Aplicar** lo hace todo de una vez, y queda en el Historial con su Deshacer. **Más tarde** la vuelve a sacar al día siguiente.
- **Lo que dejas** sigue saliendo cada semana (ya marcado «Dejar»). Pasadas 4 semanas desde la primera vez, se queda para siempre y deja de salir.

### Sincronización OneDrive ↔ G: ↔ H:

- **OneDrive en el centro:**
  - **G:** (por ejemplo, el Drive de la universidad) recibe solo `1 - Universidad UPF`.
  - **H:** (por ejemplo, el Drive personal) recibe todas las carpetas principales.
  - Qué recibe cada copia se elige en `[[sincro.copias]]` de `config.toml`.
  - G: y H: nunca se sincronizan directamente: todo pasa por OneDrive. Un cambio hecho en G: llega a H: en la misma pasada.
- **Cuándo:** al encender el PC (a los 90 segundos) y luego cada hora; también con «Sincronizar ahora». Solo mira tamaño y fecha; lee el contenido únicamente de lo que ha cambiado.
- **Qué cuenta como cambio:** crear, modificar, renombrar o mover (se mueve, no se copia de nuevo) y borrar.
  - **Lo borrado** en un sitio va a la papelera en los otros.
  - **Un conflicto** (el mismo archivo cambiado en dos sitios entre pasadas) guarda las dos versiones: la otra queda como «Nombre (conflicto AAAA-MM-DD)».
- **Seguridad:**
  - **Si G: o H: no responde** (Drive cerrado), ese sitio se salta: nunca cuenta como «se ha borrado todo».
  - **Si una pasada fuera a mandar a la papelera más de 20 archivos**, se para y abre una ventana para que elijas: «Recuperarlos» o «Mandarlos a la papelera en todos». Lo que elijas se aplica en la pasada siguiente, que empieza sola.
  - **Si mueves o renombras carpetas a un repo que estás usando**, no pregunta: espera a que el repo lleve 10 minutos quieto y entonces lo mueve también en G: y H:, de una vez.
  - **Si H: no tiene espacio**, lo que no cabe espera a la siguiente pasada y avisa.
- **Repos git:** solo van de OneDrive a G: y H:, y solo cuando llevan 10 minutos sin cambios. Lo que cambies dentro de un repo en G: o H: no se trae: se repone el de OneDrive y lo otro va a la papelera.
- **Lo que no se sincroniza:**
  - los accesos directos de Google (`.gdoc`, `.gsheet`, `.gslides`), `desktop.ini`, `~$…` y temporales;
  - la carpeta `_exportados_docs`, reservada para la fase 4.
- **Qué hizo la última pasada:** está en `datos\sincro_plan.txt`. Cada pasada con cambios queda en el Historial, y su «Deshacer» recupera lo que esa pasada mandó a la papelera.

### Copias en Word de los Google Docs

- **Escribe siempre en el Google Doc**, en G: dentro de las carpetas de la uni (o en H:, en las carpetas principales). **Nunca en el Word.**
- **Qué hace el script de Google:** está instalado en las dos cuentas (`apps_script/exportar_docs.gs`). Cada 15 minutos exporta a Word los Docs nuevos o cambiados y los deja en `Mi unidad\_exportados_docs`, con un `manifest.json`. Funciona en la nube aunque el PC esté apagado.
- **Qué hace el PC, en cada sincronización:** coloca cada Word en OneDrive, en la misma carpeta que su Doc y con su nombre, en **solo lectura**.
  - Doc cambiado → Word actualizado.
  - Doc renombrado o movido → el Word también.
  - Doc borrado → Word a la papelera.
- **Dónde se ve cada cosa:**
  - el Word de un Doc de la UPF va a OneDrive y H:, nunca a G:;
  - el de un Doc personal va a OneDrive (y a G: si está en la uni), nunca a H:.
- **Si alguien edita el Word,** no se pisa: se aparta como «Nombre (editado en Word AAAA-MM-DD).docx».
- **Si ya tienes un Word tuyo con el mismo nombre,** la copia se llama «Nombre (Doc).docx».
- **PDF definitivo:** si aparece un PDF con el mismo nombre (o el mismo texto) que un Doc, el programa **pregunta** si borra el Doc editable. Nunca lo decide solo. Si lo borras, el Doc va a la papelera de Drive (se recupera desde drive.google.com) y su Word lo sigue.
- **Para quitar o reinstalar el script:** en script.google.com, en el proyecto de cada cuenta, ejecuta «desinstalar» o «instalar».

## El icono junto al reloj

| Opción | Qué hace |
|---|---|
| Pendientes (clic izquierdo) | Lo que sigue en Descargas y cuándo irá a la Papelera. «Organizar» (o doble clic) vuelve a abrir la ventanita; «Abrir» abre el archivo. |
| Revisión semanal | Abre el resumen y la revisión de capturas cuando quieras, sin esperar al lunes. |
| Sincronizar ahora | Hace una pasada de sincronización ya. En el menú pone cuándo fue la última. |
| Borrados por confirmar | Solo aparece si la sincronización se ha parado por un borrado masivo. |
| Historial | Todo lo que ha hecho el programa en los últimos 30 días. Marca una fila: **Deshacer** la devuelve como estaba (lo que fue a la Papelera vuelve de allí, salvo que la hayas vaciado) y **Ver archivos** (o doble clic) enseña cada archivo que tocó, con su ruta entera. |
| Pausar / Reanudar | Durante una hora, o hasta que lo reanudes. En pausa, el icono se pone gris. |
| Editar lo aprendido | Abre `aprendido.txt`. |
| Abrir configuración | Abre `config.toml`. |
| Salir | Cierra el programa hasta el siguiente arranque, o hasta que lo abras desde el menú Inicio («Organizador del PC»). |

**Las listas de archivos** (Pendientes, Historial, borrados por confirmar, conflictos y duplicados) enseñan cada nombre entero y su carpeta. Lo que no cabe se ve con la barra de abajo o con Mayús + rueda del ratón, y la ventana se puede agrandar. Doble clic en un archivo: abrir su carpeta en el Explorador.

## Si deja de responder

El programa se vigila a sí mismo. Si la ventana o el icono dejan de responder 2 minutos (sin contar cuando el PC está en suspensión), o si se para alguna de sus tareas, **se reinicia solo** y te avisa. Lo apunta en `datos\cuelgues.log`. Además, cada 5 minutos repasa Descargas por si Windows no avisó de alguna descarga.

## Cómo decide la carpeta

Las pistas van de más fiable a menos:

1. **`aprendido.txt`:** de qué curso, recurso de Aula Global o web viene la descarga. Cada vez que aceptas, aprende o corrige esto él solo.
   - De las webs que sirven para todo (Drive, Gmail, WhatsApp, claude.ai, ChatGPT…, la lista `webs_genericas` de `config.toml`) no aprende nada.
   - Si de una web guardas cosas en sitios distintos, deja de usarla como pista.
2. **El contenido:** se compara el título y el texto del PDF con lo que ya tienes en cada carpeta.
3. **La categoría** (Teoría, Exámenes…) sale de palabras como tema, examen, seminari, pràctica…

**Las asignaturas son las carpetas que existan en `1 - Universidad UPF`.** Cuando empiece una nueva, crea su carpeta (o elige «Nueva carpeta…» en «Cambiar…») y el programa ya la conoce.

## Editar lo aprendido

Abre `aprendido.txt` con el Bloc de notas: icono → «Editar lo aprendido». Cada línea es

```
curso 90444 = 1 - Universidad UPF\2n - T1 - Probabilitat
web dictionary.cambridge.org = 6 - Idiomas\Inglés\B2 First (2022-24)
```

- Para que olvide algo, borra la línea.
- Los cambios cuentan desde la siguiente descarga, sin reiniciar nada.

## Configuración

`config.toml`, con el Bloc de notas: rutas, carpetas excluidas, minutos de inactividad, días del historial…

- **`simulacion = true`:** no mueve nada, solo anota en el historial lo que haría.
- **`simulacion = false`:** funciona de verdad.

Tras cambiar algo: icono → Salir, y vuelve a abrirlo desde el menú Inicio.

## Archivos

| Qué | Dónde |
|---|---|
| Programa | `organizador\` y `organizador.pyw` |
| Lo que puedes editar | `config.toml` y `aprendido.txt` |
| Datos del programa | `datos\`: `indice.sqlite` (huellas), `historial.sqlite` (historial y Pendientes) y `registro.log` (lo que pasa, por si algo falla). Si alguna vez el programa deja de responder, `cuelgues.log` dice en qué estaba y cuándo se reinició |
| Entorno de Python propio | `.venv\` |
| Pruebas | `tests\` (cómo lanzarlas: en `docs\TRASPASO.md`) |
| Scripts de Google | `apps_script\exportar_docs.gs` (el que está instalado en tus dos cuentas) |
| Detalles técnicos | `docs\TRASPASO.md`: cómo funciona por dentro, decisiones y cómo tocarlo sin romper nada. Es lo que hay que pasar a otra conversación con Claude |

## Arranque con Windows

```
.venv\Scripts\python.exe instalar.py
```

Crea el acceso directo en Inicio (arranque) y en el menú Inicio.

## Cambiar de ordenador (o reinstalar)

El programa está en un repositorio privado de GitHub, y tus datos, en la copia semanal de OneDrive.

1. Instala **Python** (3.14 o posterior) y **Git**.
2. Descarga el programa en `C:\Users\<tu usuario>\OrganizadorPC`:
   ```
   git clone https://github.com/Rxbyy06/organizador-pc.git C:\Users\<tu usuario>\OrganizadorPC
   ```
3. Instala lo que necesita:
   ```
   cd C:\Users\<tu usuario>\OrganizadorPC
   python -m venv .venv
   .venv\Scripts\python.exe -m pip install -r requirements.txt
   ```
4. Si es la primera vez: copia `config.example.toml` como `config.toml` y `aprendido.example.txt` como `aprendido.txt`, y pon tus rutas y carpetas en `config.toml`.
   Si vienes de otro PC: abre el último `Organizador AAAA-MM-DD.zip` de tu carpeta de copias y:
   - copia su carpeta `datos\` dentro de `OrganizadorPC`;
   - copia `aprendido.txt` y `config.toml` junto a `organizador.pyw`.
5. Si cambian las rutas (otro nombre de usuario, otras letras de unidad), corrígelas en `config.toml`.
6. Ejecuta `.venv\Scripts\python.exe instalar.py` para que arranque con Windows.

**Si no tienes la copia de los datos,** también funciona:
- el índice se rehace solo;
- el sincronizador vuelve a crear su estado con `python -m organizador.herramientas sincro-inicial`, si los tres sitios están iguales;
- solo se pierde el historial.

## Desinstalar

1. Icono → Salir.
2. Quita el arranque con Windows:
   ```
   .venv\Scripts\python.exe instalar.py --quitar
   ```
3. Manda la carpeta `OrganizadorPC` a la Papelera.

No toca nada de tus carpetas.
