#!/bin/bash
echo "========================================"
echo "  MobilityOS — Starting Server"
echo "========================================"

cd "$(dirname "$0")/backend"

if [ ! -f ".env" ]; then
    echo "Creating .env from template..."
    cp .env.example .env
    echo ""
    echo "⚠️  IMPORTANT: Edit backend/.env and add your API keys:"
    echo "   - GOOGLE_MAPS_KEY"
    echo "   - OPENAI_KEY"
    echo ""
    read -p "Press Enter after editing .env to continue..."
fi

echo "Installing dependencies..."
pip install -r requirements.txt --break-system-packages -q

echo ""
echo "🚀 Starting MobilityOS on http://localhost:8000"
echo "   Press Ctrl+C to stop"
echo ""
python main.py
