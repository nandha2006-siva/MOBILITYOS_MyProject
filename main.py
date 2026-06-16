import os
import json
import math
import time
import random
import asyncio
import re
from typing import Optional, List
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv
import httpx
from openai import AsyncOpenAI

# Import DB and Transport Engine
import database
from database import db_query, db_execute, get_db_connection, MOCK_MODE
from transport_engine import TransportGraphEngine, haversine

load_dotenv()


OPENAI_KEY      = os.getenv("OPENAI_KEY", "")
SECRET          = os.getenv("SECRET", "mobilityos-secret")

openai_client = AsyncOpenAI(api_key=OPENAI_KEY)

app = FastAPI(title="MobilityOS API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Database on Startup
@app.on_event("startup")
async def on_startup():
    print("[DB] Initializing PostgreSQL Database...")
    database.init_db()

# User details dependency
def get_user_email(authorization: Optional[str] = Header(None)):
    if authorization and authorization.startswith("Bearer tok_"):
        return authorization.replace("Bearer tok_", "")
    return "demo@mobilityos.in"

# ─── Static frontend ───────────────────────────────────────────────────────────
frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
app.mount("/static", StaticFiles(directory=os.path.join(frontend_path, "static")), name="static")

@app.get("/")
async def root():
    return FileResponse(os.path.join(frontend_path, "index.html"))

@app.get("/{page}.html")
async def pages(page: str):
    p = os.path.join(frontend_path, f"{page}.html")
    if not os.path.exists(p):
        raise HTTPException(404)
    if page == "dashboard":
        with open(p, "r", encoding="utf-8") as f:
            content = f.read()
        # Inject real Google Maps API key
        return HTMLResponse(content)
    return FileResponse(p)

# ─── Auth ───────────────────────────────────────────────────────────────────
class LoginReq(BaseModel):
    email: str
    password: str

class SignupReq(BaseModel):
    name: str
    email: str
    password: str

class ProfileReq(BaseModel):
    name: str

@app.post("/api/login")
async def login(req: LoginReq):
    user = db_query(
        "SELECT * FROM users WHERE email = %s;",
        (req.email,),
        fetchone=True
    )
    print("LOGIN USER =", user)

    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if user["password"] != req.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return {
        "token": f"tok_{req.email}",
        "name": user["name"],
        "email": user["email"],
        "role": user["role"]
        }

@app.post("/api/signup")
async def signup(req: SignupReq):
    existing = db_query("SELECT email FROM users WHERE email = %s;", (req.email,), fetchone=True)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    success = db_execute(
        "INSERT INTO users (email, password, name, role) VALUES (%s, %s, %s, 'user');",
        (req.email, req.password, req.name)
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to create user account")
    
    return {"status": "success", "message": "User registered successfully"}

@app.post("/api/user/profile")
async def update_profile(req: ProfileReq, user_email: str = Depends(get_user_email)):
    success = db_execute(
        "UPDATE users SET name = %s WHERE email = %s;",
        (req.name, user_email)
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update profile name")
    return {"status": "success", "name": req.name}
class JourneyReq(BaseModel):
    message: str
    history: List[dict] = []

LOCAL_NODES = {
    "karpagam college": {"lat": 10.9022, "lng": 76.9628},
    "othakkalmandapam": {"lat": 10.8872, "lng": 76.9585},
    "eachanari": {"lat": 10.9184, "lng": 76.9691},
    "sundarapuram": {"lat": 10.9526, "lng": 76.9745},
    "ukkadam": {"lat": 10.9870, "lng": 76.9620},
    "coimbatore junction": {"lat": 11.0001, "lng": 76.9669},
    "coimbatore": {"lat": 11.0168, "lng": 76.9558},
    "gandhipuram": {"lat": 11.0182, "lng": 76.9715},
    "chennai central": {"lat": 13.0827, "lng": 80.2707},
    "chennai": {"lat": 13.0827, "lng": 80.2707},
    "koyambedu": {"lat": 13.0694, "lng": 80.2078},
    "guindy": {"lat": 13.0067, "lng": 80.2206},
    "tambaram": {"lat": 12.9249, "lng": 80.1462},
    "madurai": {"lat": 9.9197, "lng": 78.1102},
    "trichy": {"lat": 10.7850, "lng": 78.6830},
    "salem": {"lat": 11.6680, "lng": 78.1180},
    "pollachi": {"lat": 10.6588, "lng": 77.0076},
    "ooty": {"lat": 11.4102, "lng": 76.6950}
}

async def geocode_address(address: str):
    addr_lower = address.lower().strip()
    # Check local nodes first
    for k, v in LOCAL_NODES.items():
        if k in addr_lower or addr_lower in k:
            return v["lat"], v["lng"], k.title()

    if not GOOGLE_MAPS_KEY or GOOGLE_MAPS_KEY == "your_google_maps_api_key_here":
        return 11.0168, 76.9558, address.title()

    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": f"{address}, Tamil Nadu, India", "key": GOOGLE_MAPS_KEY}
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(url, params=params, timeout=10)
            data = r.json()
            if data.get("status") == "OK":
                loc = data["results"][0]["geometry"]["location"]
                formatted = data["results"][0]["formatted_address"].split(",")[0]
                return loc["lat"], loc["lng"], formatted
    except Exception as e:
        print(f"Geocoding error: {e}")
    return 11.0168, 76.9558, address.title()

graph_engine = TransportGraphEngine()

@app.post("/api/journey/chat")
async def journey_chat(req: JourneyReq, user_email: str = Depends(get_user_email)):
    """Backend-calculated journey planning route formatted and summarized by OpenAI."""
    # Parse origin/destination names from message: e.g. "from karpagam to chennai"
    origin = "Karpagam College"
    destination = "Chennai Central"
    
    match = re.search(r"from\s+([a-zA-Z\s0-9]+)\s+to\s+([a-zA-Z\s0-9]+)", req.message, re.IGNORECASE)
    if match:
        origin = match.group(1).strip()
        destination = match.group(2).strip()
    else:
        # Fallback search inside chat message for single names
        found = []
        for k in LOCAL_NODES.keys():
            if k in req.message.lower():
                found.append(k.title())
        if len(found) >= 2:
            origin = found[0]
            destination = found[1]
        elif len(found) == 1:
            destination = found[0]

    # Geocode locations
    o_lat, o_lng, o_name = await geocode_address(origin)
    d_lat, d_lng, d_name = await geocode_address(destination)

    # Calculate optimal multi-modal routes using local Transport Graph
    route_data = graph_engine.plan_route(o_lat, o_lng, d_lat, d_lng, o_name, d_name)

    # Save to search journey history in DB
    db_execute(
        "INSERT INTO journeys (user_email, origin, destination, route_details) VALUES (%s, %s, %s, %s);",
        (user_email, o_name, d_name, json.dumps(route_data))
    )

    system_prompt = f"""You are MobilityOS — an AI journey planner exclusively for Tamil Nadu, India.
Our local routing engine has computed the following options for the user from {o_name} to {d_name}:
{json.dumps(route_data, indent=2)}

Your job:
1. Briefly explain the computed routes to the user in a friendly, helpful manner.
2. Summarize each option: Fastest, Cheapest, Eco-friendly, highlighting modes, times, costs, carbon savings, and women safety scores.
3. At the very end of your response, append the structured route data EXACTLY as a JSON block inside a ```route``` markdown block:
```route
{{
  "origin": "{o_name}",
  "destination": "{d_name}",
  "options": [ ... ]
}}
```
Never hallucinate transport schedules, coordinates, or different pricing. Use the computed data exactly."""

    messages = [{"role": "system", "content": system_prompt}]
    for m in req.history[-6:]:
        messages.append(m)
    messages.append({"role": "user", "content": req.message})

    try:
        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=1000,
            temperature=0.4,
        )
        reply = response.choices[0].message.content
        usage = response.usage.total_tokens
    except Exception as e:
        # If OpenAI fails, print directly
        formatted_json = json.dumps(route_data, indent=2)
        reply = f"Here is your computed multi-modal route from {o_name} to {d_name}.\n\n```route\n{formatted_json}\n```"
        usage = 0

    return {"reply": reply, "usage": usage}

# ─── Directions & Geocoding endpoints (retained for maps display) ─────────────
class DirectionsReq(BaseModel):
    origin: str
    destination: str
    mode: str = "driving"

@app.post("/api/maps/directions")
async def get_directions(req: DirectionsReq):
    url = "https://maps.googleapis.com/maps/api/directions/json"
    params = {
        "origin": f"{req.origin}, Tamil Nadu, India",
        "destination": f"{req.destination}, Tamil Nadu, India",
        "mode": req.mode,
        "alternatives": "true",
        "key": GOOGLE_MAPS_KEY,
    }
    async with httpx.AsyncClient() as client:
        r = await client.get(url, params=params, timeout=10)
        return r.json()

class GeoReq(BaseModel):
    address: str

@app.post("/api/maps/geocode")
async def geocode(req: GeoReq):
    lat, lng, name = await geocode_address(req.address)
    return {"results": [{"geometry": {"location": {"lat": lat, "lng": lng}}, "formatted_address": name}], "status": "OK"}

# ─── Women Safety ────────────────────────────────────────────────────────────
class SafetyReq(BaseModel):
    origin: str
    destination: str

@app.post("/api/safety/route")
async def safety_route(req: SafetyReq):
    def find_db_safety(name: str):
        # Clean area name
        n = name.lower().strip()
        row = db_query("SELECT area, lighting, crowd, crime, safety_score FROM safety_reports WHERE LOWER(area) LIKE %s OR %s LIKE LOWER(area);", (f"%{n}%", f"%{n}%"))
        if row:
            return row["area"], row["safety_score"], "safe" if row["safety_score"] >= 75 else "moderate" if row["safety_score"] >= 65 else "caution"
        # Fallback default
        return name, 72, "moderate"

    o_city, o_score, o_lvl = find_db_safety(req.origin)
    d_city, d_score, d_lvl = find_db_safety(req.destination)

    avg_score = round((o_score + d_score) / 2)
    tips = [
        "Share live location with a trusted contact before boarding",
        "Prefer verified cab/auto with displayed driver ID",
        "Avoid boarding at isolated stops after 9 PM",
        "Keep emergency contacts ready — use SOS button if needed",
        "Use well-lit, main road routes only"
    ]
    if avg_score < 70:
        tips.insert(0, "⚠️ This route passes through areas with safety concerns — travel during daylight if possible")

    # Insert log to safety reports if not present or log request
    db_execute("INSERT INTO safety_reports (area, lighting, crowd, crime, safety_score) VALUES (%s, 70, 60, 20, %s) ON CONFLICT DO NOTHING;", (o_city, o_score))

    return {
        "origin": {"city": o_city, "score": o_score, "level": o_lvl},
        "destination": {"city": d_city, "score": d_score, "level": d_lvl},
        "route_safety_score": avg_score,
        "recommendation": "safe" if avg_score >= 75 else "moderate" if avg_score >= 65 else "caution",
        "tips": tips,
        "sos_contacts": ["112 (Police)", "181 (Women Helpline)", "1091 (Women Safety)"]
    }

# ─── Safety Contacts CRUD ────────────────────────────────────────────────────
class ContactReq(BaseModel):
    name: str
    phone: str
    relationship: str

@app.get("/api/safety/contacts")
async def get_contacts(user_email: str = Depends(get_user_email)):
    contacts = db_query("SELECT * FROM sos_contacts WHERE user_email = %s ORDER BY id ASC;", (user_email,), fetchall=True)
    return contacts or []

@app.post("/api/safety/contacts")
async def add_contact(req: ContactReq, user_email: str = Depends(get_user_email)):
    db_execute(
        "INSERT INTO sos_contacts (user_email, contact_name, phone_number, relationship) VALUES (%s, %s, %s, %s);",
        (user_email, req.name, req.phone, req.relationship)
    )
    return {"status": "success"}

@app.delete("/api/safety/contacts/{contact_id}")
async def delete_contact(contact_id: int, user_email: str = Depends(get_user_email)):
    db_execute("DELETE FROM sos_contacts WHERE id = %s AND user_email = %s;", (contact_id, user_email))
    return {"status": "success"}

# ─── Carbon Tracker ──────────────────────────────────────────────────────────
class CarbonReq(BaseModel):
    mode: str
    distance_km: float

CARBON_FACTORS = {
    "train": 14, "metro": 10, "bus": 68, "auto": 150,
    "bike": 110, "electric_auto": 40, "walk": 0, "cycle": 0, "cab": 180
}

@app.post("/api/carbon/calculate")
async def carbon_calc(req: CarbonReq, user_email: str = Depends(get_user_email)):
    factor = CARBON_FACTORS.get(req.mode.lower(), 100)
    emissions_g = factor * req.distance_km
    baseline_car = 192 * req.distance_km
    saved_g = max(0.0, baseline_car - emissions_g)
    trees_equiv = round(saved_g / 21000, 3)
    points = int(saved_g / 100)

    # Insert carbon logs
    db_execute(
        "INSERT INTO carbon_logs (user_email, mode, distance_km, emissions_g, saved_g) VALUES (%s, %s, %s, %s, %s);",
        (user_email, req.mode, req.distance_km, emissions_g, saved_g)
    )
    
    # Award reward points
    if points > 0:
        db_execute(
            "INSERT INTO reward_points (user_email, points, reason) VALUES (%s, %s, %s);",
            (user_email, points, f"Travelled {req.distance_km}km via {req.mode}")
        )
        # Add to trip history
        db_execute(
            "INSERT INTO trip_history (user_email, origin, destination, mode, distance_km, carbon_saved_g, points_earned) VALUES (%s, 'My Location', 'Destination', %s, %s, %s, %s);",
            (user_email, req.mode, req.distance_km, saved_g, points)
        )

    # Fetch total points
    total_pts_row = db_query("SELECT SUM(points) FROM reward_points WHERE user_email = %s;", (user_email,))
    total_points = int(total_pts_row["sum"]) if total_pts_row and total_pts_row["sum"] else 0

    return {
        "mode": req.mode,
        "distance_km": req.distance_km,
        "emissions_g": emissions_g,
        "carbon_factor_g_per_km": factor,
        "saved_vs_car_g": saved_g,
        "trees_equivalent": trees_equiv,
        "reward_points": points,
        "total_points": total_points,
        "grade": "A+" if factor == 0 else "A" if factor < 20 else "B" if factor < 80 else "C",
    }

@app.get("/api/carbon/leaderboard")
async def carbon_leaderboard():
    """Fetch top users ranking and carbon saved from PostgreSQL."""
    query = """
        SELECT name, COALESCE(SUM(points), 0) as points 
        FROM users 
        LEFT JOIN reward_points ON users.email = reward_points.user_email
        GROUP BY users.email, users.name 
        ORDER BY points DESC LIMIT 5;
    """
    board = db_query(query, fetchall=True)
    if not board:
        # Fallback if DB is empty
        return [
            {"name": "Gopi", "points": 2840},
            {"name": "Admin", "points": 500},
            {"name": "Ramya", "points": 420},
            {"name": "Suresh", "points": 290}
        ]
    return board

@app.post("/api/carbon/claim-reward")
async def claim_reward(user_email: str = Depends(get_user_email)):
    # Deduct 500 points
    db_execute("INSERT INTO reward_points (user_email, points, reason) VALUES (%s, -500, 'Claimed weekly coffee reward');", (user_email,))
    
    total_pts_row = db_query("SELECT SUM(points) FROM reward_points WHERE user_email = %s;", (user_email,))
    total_points = int(total_pts_row["sum"]) if total_pts_row and total_pts_row["sum"] else 0
    return {"status": "success", "total_points": total_points}

# ─── Fare Estimation ─────────────────────────────────────────────────────────
class FareReq(BaseModel):
    mode: str
    distance_km: float
    time_of_day: str = "day"

FARE_BASE = {
    "auto":  {"base": 30, "per_km": 15, "night_mult": 1.5},
    "bus":   {"base": 10, "per_km": 1.2, "night_mult": 1.0},
    "train": {"base": 25, "per_km": 0.5, "night_mult": 1.0},
    "metro": {"base": 10, "per_km": 2.0, "night_mult": 1.0},
    "bike":  {"base": 20, "per_km": 7,   "night_mult": 1.2},
    "cab":   {"base": 50, "per_km": 18,  "night_mult": 1.3},
}

@app.post("/api/fare/estimate")
async def fare_estimate(req: FareReq):
    f = FARE_BASE.get(req.mode.lower(), {"base": 30, "per_km": 10, "night_mult": 1.0})
    base_fare = f["base"] + f["per_km"] * req.distance_km
    mult = f["night_mult"] if req.time_of_day in ["night", "peak"] else 1.0
    if req.time_of_day == "peak":
        mult = min(mult * 1.2, 2.0)
    final = round(base_fare * mult, 2)
    return {
        "mode": req.mode,
        "distance_km": req.distance_km,
        "time_of_day": req.time_of_day,
        "estimated_fare_inr": final,
        "range": {"min": round(final * 0.9), "max": round(final * 1.15)},
        "surge": req.time_of_day in ["night", "peak"],
    }

# ─── Train info ─────────────────────────────────────────────────────────────
@app.get("/api/trains/{origin}/{destination}")
async def train_info(origin: str, destination: str):
    from database import MOCK_DB
    trains = db_query(
        "SELECT * FROM trains WHERE LOWER(origin) LIKE %s AND LOWER(destination) LIKE %s;",
        (f"%{origin.lower()}%", f"%{destination.lower()}%"),
        fetchall=True
    )
    if not trains:
        res = []
        for t in MOCK_DB["trains"]:
            if origin.lower() in t["origin"].lower() and destination.lower() in t["destination"].lower():
                res.append(t)
        trains = res
    return {
        "origin": origin,
        "destination": destination,
        "date": "today",
        "trains": trains,
        "note": "Train schedules loaded."
    }

# ─── Bus info ──────────────────────────────────────────────────────────────
@app.get("/api/buses/{origin}/{destination}")
async def bus_info(origin: str, destination: str):
    routes = db_query("SELECT * FROM tnstc_routes;", fetchall=True)
    if not routes:
        from database import MOCK_DB
        routes = MOCK_DB["tnstc_routes"]
    
    matching = []
    o_lower = origin.lower().strip()
    d_lower = destination.lower().strip()
    
    for r in routes:
        stops = r["stops"]
        if isinstance(stops, str):
            try:
                import json
                stops = json.loads(stops)
            except:
                stops = []
        
        stops_lower = [s.lower() for s in stops]
        
        o_idx = -1
        d_idx = -1
        for idx, s in enumerate(stops_lower):
            if o_lower in s or s in o_lower:
                o_idx = idx
            if d_lower in s or s in d_lower:
                d_idx = idx
        
        if o_idx != -1 and d_idx != -1 and o_idx < d_idx:
            matching.append({
                "bus_no": r["bus_no"],
                "stops": stops,
                "frequency_min": r["frequency_min"],
                "travel_time_min": r["travel_time_min"],
                "origin": stops[o_idx],
                "destination": stops[d_idx],
                "stops_in_between": stops[o_idx+1:d_idx]
            })
            
    return {
        "origin": origin,
        "destination": destination,
        "buses": matching
    }

# ─── Live Tracking WebSocket with Deviation and Traffic Intelligence ─────────
class ConnectionManager:
    def __init__(self):
        self.active: List[WebSocket] = []
    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)
    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)
    async def send(self, ws: WebSocket, data: dict):
        await ws.send_json(data)

manager = ConnectionManager()

@app.websocket("/ws/tracking")
async def tracking_ws(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            
            # Extract client telemetry
            lat = payload.get("lat")
            lng = payload.get("lng")
            speed = payload.get("speed") or random.randint(20, 60)
            user_email = payload.get("email") or "demo@mobilityos.in"
            
            # Polyline points for route deviation checking
            expected_route = payload.get("expected_route", [])
            
            # Find closest polyline point and check deviation
            deviation = False
            if expected_route and len(expected_route) > 0:
                min_dist = float('inf')
                for pt in expected_route:
                    # pt can be [lat, lng] or {"lat": x, "lng": y}
                    pt_lat = pt[0] if isinstance(pt, list) else pt.get("lat")
                    pt_lng = pt[1] if isinstance(pt, list) else pt.get("lng")
                    dist = haversine(lat, lng, pt_lat, pt_lng)
                    if dist < min_dist:
                        min_dist = dist
                # If closest point is > 500m (0.5km), route deviation detected!
                if min_dist > 0.5:
                    deviation = True

            # Register SOS alerts automatically in database upon deviation or SOS click
            sos_triggered = payload.get("sos_triggered", False)
            if sos_triggered or deviation:
                driver_name = payload.get("driver_name", "Unknown Driver")
                driver_phone = payload.get("driver_phone", "No Phone Details")
                vehicle_num = payload.get("vehicle_number", "No Vehicle Plate")
                
                db_execute(
                    "INSERT INTO sos_alerts (user_email, lat, lng, driver_name, driver_phone, vehicle_number) VALUES (%s, %s, %s, %s, %s, %s);",
                    (user_email, lat, lng, driver_name, driver_phone, vehicle_num)
                )

            # Traffic Intelligence
            traffic = "clear"
            if speed < 15:
                traffic = "heavy"
            elif speed < 35:
                traffic = "moderate"
                
            current_delay = 15 if traffic == "heavy" else 5 if traffic == "moderate" else 0
            
            # Predict delay in 30 minutes
            predicted_delay = current_delay
            if traffic == "heavy":
                predicted_delay = int(current_delay * 1.6 + random.randint(2, 6))
            elif traffic == "moderate":
                predicted_delay = int(current_delay * 1.4 + random.randint(1, 4))
            else:
                # predicted peak hour delay
                predicted_delay = random.choice([0, 0, 5, 8])

            eta = max(5, int(payload.get("eta_min", 45) - 1))

            await manager.send(websocket, {
                "lat": lat, "lng": lng,
                "speed_kmh": speed,
                "traffic": traffic,
                "delay_min": current_delay,
                "predicted_delay_30min": predicted_delay,
                "route_deviation": deviation,
                "eta_min": eta,
                "timestamp": int(time.time()),
            })
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WS Exception: {e}")
        manager.disconnect(websocket)

# ─── Admin Metrics Dashboard Endpoint ───────────────────────────────────────
@app.get("/api/admin/metrics")
async def admin_metrics(user_email: str = Depends(get_user_email)):
    print("TOKEN EMAIL =", user_email)
    user = db_query(
        "SELECT role FROM users WHERE email = %s;",
        (user_email,),fetchone=True
    )
    print("DB USER =", user)
    if not user or user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Access denied: Admins only")

    # 1. Total users count
    u_count = db_query("SELECT COUNT(*) AS count FROM users;")
    total_users = u_count["count"] if u_count else 2
    
    # 2. Total trips count
    t_count = db_query("SELECT COUNT(*) AS count FROM trip_history;")
    total_trips = t_count["count"] if t_count else 4
    
    # 3. Carbon Saved (kg)
    carbon_saved_res = db_query("SELECT SUM(carbon_saved_g) AS sum FROM trip_history;")
    carbon_saved = round((carbon_saved_res["sum"] or 0) / 1000, 2) if carbon_saved_res and carbon_saved_res["sum"] is not None else 4.2
    
    # 4. SOS alerts count & active alerts logs
    alerts = db_query("SELECT * FROM sos_alerts ORDER BY id DESC LIMIT 10;", fetchall=True) or []
    sos_count = len(alerts)
    print("SOS COUNT =", sos_count)
    print("ALERTS =", alerts)
    # 5. Popular routes
    routes = db_query("SELECT origin, destination, COUNT(*) AS trip_count FROM journeys GROUP BY origin, destination ORDER BY count DESC LIMIT 5;", fetchall=True) or []
    popular_routes = [{"origin": r["origin"], "destination": r["destination"], "count": r["count"]} for r in routes]
    if not popular_routes:
        popular_routes = [
            {"origin": "Coimbatore", "destination": "Chennai", "count": 142},
            {"origin": "Karpagam College", "destination": "Gandhipuram", "count": 98},
            {"origin": "Othakalmandapam", "destination": "Coimbatore Junction", "count": 65}
        ]

    # Traffic Congestion levels list
    traffic_logs = [
        {"route": "NH-544 (Coimbatore-Salem)", "congestion": "Heavy Delay (25 min)", "status": "red"},
        {"route": "GST Road (Tambaram-Guindy)", "congestion": "Moderate Delay (10 min)", "status": "yellow"},
        {"route": "Gandhipuram Flyover", "congestion": "Clear Flow", "status": "green"}
    ]

    # Detailed metrics for admin users management
    users_list = db_query("SELECT name, email, role FROM users;", fetchall=True) or []
    journeys_list = db_query("SELECT user_email, origin, destination, route_details, created_at FROM journeys ORDER BY created_at DESC;", fetchall=True) or []
    trips_list = db_query("SELECT user_email, origin, destination, mode, distance_km, carbon_saved_g, points_earned, created_at FROM trip_history ORDER BY created_at DESC;", fetchall=True) or []

    return {
        "total_users": total_users,
        "total_trips": total_trips,
        "carbon_saved_kg": carbon_saved,
        "sos_count": sos_count,
        "sos_alerts": alerts,
        "popular_routes": popular_routes,
        "traffic_logs": traffic_logs,
        "users": users_list,
        "journeys": journeys_list,
        "trip_history": trips_list
    }

if __name__ == "__main__":
    import uvicorn
    import webbrowser
    import threading
    import time

    def open_browser():
        time.sleep(1.5)
        try:
            webbrowser.open("http://localhost:8000")
        except Exception as e:
            print(f"[ERROR] Could not open browser: {e}")

    threading.Thread(target=open_browser, daemon=True).start()
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
