# 🚌 MobilityOS — Tamil Nadu AI Mobility Platform

> AI-powered journey planning, women safety, carbon tracking, fare estimation, and live tracking for Tamil Nadu.

---

## 📁 Project Structure

```
mobilityos/
├── backend/
│   ├── main.py            ← FastAPI backend (all APIs)
│   ├── requirements.txt   ← Python dependencies
│   ├── .env.example       ← API key template
│   └── .env               ← YOUR keys (create from example)
├── frontend/
│   ├── index.html         ← Login page
│   └── dashboard.html     ← Full dashboard (all features)
├── start.sh               ← Mac/Linux launcher
├── start.bat              ← Windows launcher
└── README.md
```

---

## ⚡ Quick Start

### Step 1 — Add your API keys

```bash
cd backend
cp .env.example .env
```

Edit `.env`:
```
GOOGLE_MAPS_KEY=your_actual_google_maps_key
OPENAI_KEY=your_actual_openai_key
```

### Step 2 — Install & Run

**Mac/Linux:**
```bash
chmod +x start.sh
./start.sh
```

**Windows:**
```
Double-click start.bat
```

**Or manually:**
```bash
cd backend
pip install -r requirements.txt
python main.py
```

### Step 3 — Open browser
```
http://localhost:8000
```

**Demo login:**
- Email: `demo@mobilityos.in`
- Password: `demo1234`

---

## 🗺️ Google Maps API Setup

In [Google Cloud Console](https://console.cloud.google.com):

Enable these APIs for your key:
- ✅ Maps JavaScript API
- ✅ Directions API
- ✅ Geocoding API
- ✅ Places API

Add `http://localhost:8000` to **Authorized HTTP referrers**.

---

## 🤖 Features

### 1. Journey Planner (AI + Google Maps)
- Chat or voice input in English/Tamil
- OpenAI GPT-4o-mini analyzes your query
- Google Maps Directions API for real routes
- Multi-modal: auto → bus → train combinations
- 3 options: Fastest, Cheapest, Eco-friendly
- Train booking redirects to IRCTC
- Ride booking redirects to Ola/Rapido/Uber

### 2. Women Safety
- Route safety scoring (AI-trained TN dataset)
- Safe route highlighted in green on map
- Unsafe route highlighted in red
- Route deviation detection + alarm
- Auto-notification to emergency contacts (simulated)
- One-tap SOS: 112, 181, 1091, 108

### 3. Carbon Tracker
- Real-time CO₂ emissions per transport mode
- Compare vs private car baseline
- Daily eco-reward points
- 7-day streak tracking
- AI eco tips

### 4. Fare & Booking
- AI fare estimation (auto, bus, train, metro, cab)
- Surge detection (peak/night)
- IRCTC train search & booking
- Direct booking links: Ola, Rapido, Uber, Namma Yatri, TNSTC

### 5. Live Tracking (WebSocket)
- Real-time location updates every 3 seconds
- Traffic color coding (green/yellow/red route)
- ETA updates
- Route deviation alerts with alarm sound
- Emergency contact auto-notification

---

## 🚂 Train API Note

IRCTC does not have a free public API. Options:
- **RailwayAPI.in** (paid, ₹500/month) — add `RAPIDAPI_KEY` to `.env`
- **Confirmtkt** scraping (unofficial)
- Current implementation: realistic simulated data

---

## 🌐 Hosting (Web Server)

```bash
# Install nginx + deploy
pip install gunicorn
gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app --bind 0.0.0.0:8000

# Or use Railway/Render for free hosting:
# railway up
```

---

## 🔧 Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11 + FastAPI + Uvicorn |
| AI | OpenAI GPT-4o-mini |
| Maps | Google Maps JS + Directions + Geocoding API |
| Real-time | WebSockets |
| Frontend | Vanilla HTML/CSS/JS (Space Grotesk + Inter fonts) |
| Train | Simulated IRCTC data (swap for RailwayAPI) |

---

## 📞 Emergency Numbers (Tamil Nadu)

| Service | Number |
|---------|--------|
| Police | 112 |
| Women Helpline | 181 |
| Women Safety | 1091 |
| Ambulance | 108 |
| Child Helpline | 1098 |
