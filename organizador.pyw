"""Organizador del PC. Ábrelo con doble clic (sin ventana de consola)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from organizador.app import main

main()
