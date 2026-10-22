/**
 * Organizador del PC — copias en Word de los Google Docs (fase 4).
 *
 * Cada 15 minutos exporta a Word (.docx) los Google Docs nuevos o cambiados de las carpetas que se
 * sincronizan, y los deja en «Mi unidad/_exportados_docs/<id del Doc>.docx» junto con «manifest.json»
 * (id, nombre, carpeta y fecha de cada Doc). El Organizador del PC lee ese manifiesto y coloca cada Word
 * en OneDrive, en la misma carpeta que el Doc y con el mismo nombre.
 *
 * Qué carpetas mira: las carpetas principales de CARPETAS (ponlas iguales que en config.toml).
 * Es el mismo archivo para las dos cuentas.
 *
 * Instalación (una vez por cuenta): pegar este archivo en un proyecto nuevo de script.google.com,
 * añadir el servicio «Drive API» (Servicios → + → Drive API), elegir «instalar» → Ejecutar → autorizar.
 * Para quitarlo: ejecutar «desinstalar».
 */

var CARPETAS = ['1 - Universidad UPF', '2 - Trabajo', '3 - Idiomas', '4 - Personal'];
var SALIDA = '_exportados_docs';

function instalar() {
  desinstalar();
  ScriptApp.newTrigger('exportar').timeBased().everyMinutes(15).create();
  exportar();
  Logger.log('Instalado: exporta cada 15 minutos. Carpetas: ' + carpetas_().join(', '));
}

function desinstalar() {
  ScriptApp.getProjectTriggers().forEach(function (t) { ScriptApp.deleteTrigger(t); });
}

function carpetas_() {
  return CARPETAS;
}

function exportar() {
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(1000)) return;                 // ya hay otra ejecución en marcha
  try {
    var raiz = DriveApp.getRootFolder();
    var salida = subcarpeta_(raiz, SALIDA);
    var manifiesto = archivo_(salida, 'manifest.json');
    var previo = manifiesto ? JSON.parse(manifiesto.getBlob().getDataAsString() || '{}') : {};
    var antes = previo.docs || {};
    var docs = buscarDocs_(raiz.getId(), carpetas_());
    var token = ScriptApp.getOAuthToken();

    Object.keys(docs).forEach(function (id) {
      var d = docs[id], p = antes[id];
      if (p && p.word && p.modificado === d.modificado) {        // sin cambios: el Word de antes vale
        d.word = p.word;
        d.exportado = p.exportado;
        return;
      }
      var blob = UrlFetchApp.fetch('https://docs.google.com/document/d/' + id + '/export?format=docx',
        { headers: { Authorization: 'Bearer ' + token } }).getBlob().setName(id + '.docx');
      d.word = null;
      if (p && p.word) {
        try { Drive.Files.update({}, p.word, blob); d.word = p.word; } catch (e) { d.word = null; }
      }
      if (!d.word) d.word = salida.createFile(blob).getId();
      d.exportado = new Date().toISOString();
    });
    // Docs que ya no están (borrados o fuera de las carpetas): su Word exportado, a la papelera.
    Object.keys(antes).forEach(function (id) {
      if (!docs[id] && antes[id].word) {
        try { DriveApp.getFileById(antes[id].word).setTrashed(true); } catch (e) { }
      }
    });

    var nuevo = JSON.stringify({ version: 1, carpetas: carpetas_(), docs: docs }, null, 1);
    var viejo = JSON.stringify({ version: 1, carpetas: previo.carpetas || carpetas_(), docs: antes }, null, 1);
    if (nuevo !== viejo || !manifiesto) {                        // solo se reescribe si algo ha cambiado
      if (manifiesto) manifiesto.setContent(nuevo); else salida.createFile('manifest.json', nuevo, 'application/json');
    }
  } finally {
    lock.releaseLock();
  }
}

/** Todos los Docs propios, no borrados, que estén dentro de alguna de las carpetas. */
function buscarDocs_(raizId, carpetas) {
  var docs = {}, rutas = {};
  rutas[raizId] = '';
  var it = DriveApp.searchFiles("mimeType = 'application/vnd.google-apps.document' and trashed = false and 'me' in owners");
  while (it.hasNext()) {
    var f = it.next();
    var padres = f.getParents();
    if (!padres.hasNext()) continue;
    var ruta = ruta_(padres.next(), raizId, rutas);
    if (ruta === null) continue;                                  // no está en Mi unidad
    var primera = ruta.split('/')[0];
    if (carpetas.indexOf(primera) < 0) continue;
    docs[f.getId()] = { nombre: f.getName(), ruta: ruta, modificado: f.getLastUpdated().toISOString() };
  }
  return docs;
}

/** «1 - Universidad UPF/1r - T1 - Càlcul I/1 - Teoría» (con caché de carpetas ya vistas). */
function ruta_(carpeta, raizId, rutas) {
  var id = carpeta.getId();
  if (rutas.hasOwnProperty(id)) return rutas[id];
  var padres = carpeta.getParents();
  if (!padres.hasNext()) { rutas[id] = null; return null; }
  var arriba = ruta_(padres.next(), raizId, rutas);
  rutas[id] = arriba === null ? null : (arriba ? arriba + '/' : '') + carpeta.getName();
  return rutas[id];
}

function subcarpeta_(padre, nombre) {
  var it = padre.getFoldersByName(nombre);
  return it.hasNext() ? it.next() : padre.createFolder(nombre);
}

function archivo_(carpeta, nombre) {
  var it = carpeta.getFilesByName(nombre);
  return it.hasNext() ? it.next() : null;
}
