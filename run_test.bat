@echo off
REM Script de démarrage du test autonome Aldes API
echo.
echo ============================================================
echo   Test Autonome Aldes API
echo ============================================================
echo.

REM Vérifier si Python est installé
python --version >nul 2>&1
if errorlevel 1 (
    echo Erreur: Python n'est pas installé ou n'est pas dans le PATH
    echo Veuillez installer Python 3.10+ depuis https://www.python.org/
    pause
    exit /b 1
)

REM Vérifier si les dépendances sont installées
echo Vérification des dépendances...
python -c "import aiohttp" >nul 2>&1
if errorlevel 1 (
    echo Installation des dépendances...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo Erreur lors de l'installation des dépendances
        pause
        exit /b 1
    )
)

echo Démarrage du test autonome...
echo.

REM Lancer le script
python test_standalone.py

pause
