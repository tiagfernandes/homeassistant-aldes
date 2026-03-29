#!/usr/bin/env python3
"""Installation assistant for Aldes API test tool."""

import subprocess
import sys
from pathlib import Path


def check_python_version():
    """Check if Python version is 3.10 or higher."""
    if sys.version_info < (3, 10):
        print("❌ Python 3.10+ est requis")
        print(f"   Version actuelle: {sys.version}")
        return False
    print(f"✓ Python {sys.version.split()[0]} détecté")
    return True


def install_dependencies():
    """Install project dependencies."""
    print("\n📦 Installation des dépendances...")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"]
        )
        print("✓ Dépendances installées avec succès")
        return True
    except subprocess.CalledProcessError:
        print("❌ Erreur lors de l'installation des dépendances")
        return False


def verify_imports():
    """Verify that required modules can be imported."""
    print("\n🔍 Vérification des imports...")
    required_modules = [
        "aiohttp",
        "backoff",
        "asyncio",
    ]

    all_ok = True
    for module in required_modules:
        try:
            __import__(module)
            print(f"✓ {module}")
        except ImportError:
            print(f"❌ {module}")
            all_ok = False

    return all_ok


def main():
    """Main installation routine."""
    print("=" * 60)
    print("  ASSISTANT D'INSTALLATION - TEST ALDES API")
    print("=" * 60)

    # Check Python version
    if not check_python_version():
        sys.exit(1)

    # Install dependencies
    if not install_dependencies():
        sys.exit(1)

    # Verify imports
    if not verify_imports():
        print("\n⚠️  Erreur lors de la vérification des imports")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("✓ INSTALLATION RÉUSSIE!")
    print("=" * 60)
    print("\nVous pouvez maintenant lancer le test:")
    print("  python test_standalone.py")
    print("\nOu:")
    print("  python3 test_standalone.py")


if __name__ == "__main__":
    main()
