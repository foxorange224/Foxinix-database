#!/bin/sh

# Directorio predeterminado
cd "/home/foxorange224/Juegos/Geometry Dash/"

# Variables importantes
WINEDLLOVERRIDES="xinput1_4=n,b"
export WINEDLLOVERRIDES="xinput1_4=n,b"

# Ejecutar el juego
wine GeometryDash.exe
