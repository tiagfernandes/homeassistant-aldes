#!/bin/bash

# Script de démarrage du test autonome Aldes API

echo ""
echo "============================================================"
echo "   Test Autonome Aldes API"
echo "============================================================"
echo ""

# Vérifier si Python est installé
if ! command -v python3 &> /dev/null; then
    echo "Erreur: Python 3 n'est pas installé"
    echo "Veuillez installer Python 3.10+ depuis https://www.python.org/"
    exit 1
fi

# Vérifier si les dépendances sont installées
echo "Vérification des dépendances..."
python3 -c "import aiohttp" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "Installation des dépendances..."
    pip3 install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo "Erreur lors de l'installation des dépendances"
        exit 1
    fi
fi

echo "Démarrage du test autonome..."
echo ""

# Lancer le script
python3 test_standalone.py
