"""Arranque con Windows: crea (o quita) los accesos directos del Organizador.

    .venv\\Scripts\\python.exe instalar.py           ← arranca solo al encender el PC + entrada en el menú Inicio
    .venv\\Scripts\\python.exe instalar.py --quitar  ← deja de arrancar solo (no borra nada más)
"""
import os
import sys

import win32com.client

RAIZ = os.path.dirname(os.path.abspath(__file__))
NOMBRE = 'Organizador del PC.lnk'
SITIOS = [os.path.join(os.environ['APPDATA'], r'Microsoft\Windows\Start Menu\Programs\Startup'),
          os.path.join(os.environ['APPDATA'], r'Microsoft\Windows\Start Menu\Programs')]


def instalar() -> None:
    shell = win32com.client.Dispatch('WScript.Shell')
    for carpeta in SITIOS:
        acceso = shell.CreateShortCut(os.path.join(carpeta, NOMBRE))
        acceso.TargetPath = os.path.join(RAIZ, '.venv', 'Scripts', 'pythonw.exe')
        acceso.Arguments = f'"{os.path.join(RAIZ, "organizador.pyw")}"'
        acceso.WorkingDirectory = RAIZ
        acceso.Description = 'Organizador del PC (Descargas)'
        acceso.save()
        print('Creado:', os.path.join(carpeta, NOMBRE))


def quitar() -> None:
    for carpeta in SITIOS:
        ruta = os.path.join(carpeta, NOMBRE)
        if os.path.exists(ruta):
            os.remove(ruta)          # solo el acceso directo, no el programa
            print('Quitado:', ruta)


if __name__ == '__main__':
    quitar() if '--quitar' in sys.argv else instalar()
