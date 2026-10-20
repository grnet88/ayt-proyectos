# Instalación en Windows Server (prueba)

Probado para Windows Server 2016 o posterior y Windows 10/11. No hace falta IIS ni base de datos aparte.

## 1. Instalar Python

1. Descargar Python 3.12 para Windows (64 bits) desde https://www.python.org/downloads/windows/
2. Al instalar, marcar **"Add python.exe to PATH"** y elegir "Install Now".
3. Abrir una consola nueva (cmd) y verificar: `python --version` debe mostrar 3.11 o superior.

## 2. Copiar la aplicación

- Opción A, con Git: `git clone https://github.com/<usuario>/ayt-proyectos.git C:\AyT\ayt-proyectos`
- Opción B, sin Git: descomprimir `ayt-proyectos-v0.2.zip` en `C:\AyT\` (queda `C:\AyT\ayt-proyectos`).

## 3. Primer arranque y configuración

1. Doble clic en `C:\AyT\ayt-proyectos\iniciar-servidor.bat`. La primera vez crea el entorno e instala
   dependencias (necesita internet, tarda un minuto). Dejar esa ventana abierta: es el servidor.
2. **En el mismo servidor**, abrir el navegador en http://localhost:8000
3. Definir la contraseña de `aytroot` (botón Mostrar para verla). Se descarga
   `aytroot-llave-recuperacion.key`: moverla a un pendrive o lugar seguro fuera del servidor.

La configuración inicial y la recuperación con llave solo se aceptan desde el propio servidor
(http://localhost:8000), nunca desde otra PC.

## 4. Acceso desde otras PC de la red

1. Abrir el puerto en el firewall (consola como administrador):
   `netsh advfirewall firewall add rule name="AyT Proyectos" dir=in action=allow protocol=TCP localport=8000`
2. Desde otra PC: `http://IP-DEL-SERVIDOR:8000` (la IP sale de `ipconfig`).

## 5. Que arranque solo con el servidor (opcional)

Con el Programador de tareas, como administrador:

```
schtasks /create /tn "AyT Proyectos" /tr "C:\AyT\ayt-proyectos\iniciar-servidor.bat" /sc onstart /ru SYSTEM
```

Para detenerlo: `schtasks /end /tn "AyT Proyectos"`. Para quitarlo: `schtasks /delete /tn "AyT Proyectos" /f`.

## Datos y copias de seguridad

Todo se guarda en `C:\AyT\ayt-proyectos\datos\ayt.db`. Para respaldar, copiar ese archivo con el servidor
detenido (o programar una copia diaria). Actualizar la aplicación no toca esa carpeta.

## Actualizar

Con Git: `git pull` en la carpeta, luego `.venv\Scripts\python -m pip install -r requirements.txt`
(por si hay librerías nuevas) y reiniciar el servidor. Sin Git: descomprimir la versión nueva encima,
sin borrar la carpeta `datos`.

## Notas

- Es una versión de prueba: usa HTTP sin cifrar. Para uso fuera de la red local hará falta HTTPS (etapa 9).
- El mapa satelital necesita internet en la PC que abre la app.
