@echo off
REM Mise à jour quotidienne de la veille JORF
REM Se place dans le dossier où se trouve ce fichier avant de lancer les scripts
cd /d "%~dp0"

echo [%date% %time%] Debut mise a jour >> update.log
python fetch_cdm.py >> update.log 2>&1
python weekly_update.py >> update.log 2>&1
echo [%date% %time%] Fin mise a jour >> update.log
echo. >> update.log
