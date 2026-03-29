#!/bin/bash
# Script de vérification et de validation du projet

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  Home Assistant Aldes Integration - Validation Script         ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# 1. Ruff Check
echo "📋 1. Checking with Ruff..."
python -m ruff check .
if [ $? -eq 0 ]; then
    echo "✅ Ruff: PASSED"
else
    echo "❌ Ruff: FAILED"
    exit 1
fi
echo ""

# 2. Black Check
echo "📋 2. Checking format with Black..."
python -m black --check .
if [ $? -eq 0 ]; then
    echo "✅ Black: PASSED"
else
    echo "❌ Black: FAILED"
    exit 1
fi
echo ""

# 3. Manifest JSON
echo "📋 3. Validating manifest.json..."
python -c "import json; json.load(open('custom_components/aldes/manifest.json')); print('✅ JSON: VALID')" 2>&1
if [ $? -ne 0 ]; then
    echo "❌ JSON: INVALID"
    exit 1
fi
echo ""

# 4. Pytest
echo "📋 4. Running pytest..."
pytest tests -v
if [ $? -eq 0 ]; then
    echo "✅ Pytest: PASSED"
else
    echo "❌ Pytest: FAILED"
    exit 1
fi
echo ""

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  ✅ All checks PASSED! Ready for deployment.                  ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "Next steps:"
echo "1. git add ."
echo "2. git commit -m 'Fix: ruff, black, pytest, manifest, and asyncio issues'"
echo "3. git push origin dev"
echo ""
echo "Then verify GitHub Actions workflows pass! 🚀"

