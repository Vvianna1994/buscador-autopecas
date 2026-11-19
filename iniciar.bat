@echo off
chcp 65001 >nul
title Buscador de Autopecas
cd /d "%~dp0"
where py >nul 2>nul && (py -3 iniciar.py %* & goto fim)
where python >nul 2>nul && (python iniciar.py %* & goto fim)
echo.
echo O Python nao esta instalado.
echo Baixe em https://www.python.org/downloads/ e, na instalacao,
echo MARQUE a opcao "Add Python to PATH". Depois abra este arquivo de novo.
echo.
start https://www.python.org/downloads/
pause
:fim
