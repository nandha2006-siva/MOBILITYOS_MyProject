import os
import urllib.parse
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
print("DATABASE_URL =", DATABASE_URL)

if not DATABASE_URL:
    raise ValueError("DATABASE_URL not found in .env")

# Global flag to track if we are using a mock fallback
MOCK_MODE = False
MOCK_DB = {
    "users": {},
    "journeys": [],
    "reward_points": [],
    "trip_history": [],
    "sos_contacts": {},
    "safety_reports": {},
    "carbon_logs": [],
    "tnstc_routes": [],
    "trains": [],
    "sos_alerts": []
}

def seed_data(conn):
    """
    PostgreSQL is managed manually.
    No automatic demo users or seed data.
    """
    print("[INFO] Database already configured manually. Skipping seed data.")
    return
def get_db_connection():
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        print(f"[ERROR] DATABASE CONNECTION ERROR: {e}")
        return None
def init_db():
    global MOCK_MODE
    # First, try to connect and create the database if it doesn't exist
    try:
        # Parse connection string to connect to default 'postgres' DB first
        p = urllib.parse.urlparse(DATABASE_URL)
        username = p.username
        password = p.password
        hostname = p.hostname
        port = p.port
        
        # Connect to default postgres DB
        conn = psycopg2.connect(
            dbname="postgres",
            user=username,
            password=password,
            host=hostname,
            port=port
        )
        conn.autocommit = True
        cur = conn.cursor()
        
        # Check if mobilityos database exists
        cur.execute("SELECT 1 FROM pg_catalog.pg_database WHERE datname = 'mobilityos';")
        exists = cur.fetchone()
        if not exists:
            print("[DB] Creating database 'mobilityos'...")
            cur.execute("CREATE DATABASE mobilityos;")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"[WARNING] Could not verify/create 'mobilityos' DB on default admin level: {e}")
        print("Continuing to connect directly to the database url...")

    conn = get_db_connection()
    if not conn:
        raise Exception("Unable to connect to PostgreSQL")

    try:
        conn.autocommit = True
        cur = conn.cursor()
        
        # 1. users
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL,
                name VARCHAR(255) NOT NULL,
                role VARCHAR(50) DEFAULT 'user'
            );
        """)
        
        # 2. journeys
        cur.execute("""
            CREATE TABLE IF NOT EXISTS journeys (
                id SERIAL PRIMARY KEY,
                user_email VARCHAR(255) REFERENCES users(email) ON DELETE CASCADE,
                origin VARCHAR(255) NOT NULL,
                destination VARCHAR(255) NOT NULL,
                route_details JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # 3. reward_points
        cur.execute("""
            CREATE TABLE IF NOT EXISTS reward_points (
                id SERIAL PRIMARY KEY,
                user_email VARCHAR(255) REFERENCES users(email) ON DELETE CASCADE,
                points INTEGER NOT NULL,
                reason VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # 4. trip_history
        cur.execute("""
            CREATE TABLE IF NOT EXISTS trip_history (
                id SERIAL PRIMARY KEY,
                user_email VARCHAR(255) REFERENCES users(email) ON DELETE CASCADE,
                origin VARCHAR(255) NOT NULL,
                destination VARCHAR(255) NOT NULL,
                mode VARCHAR(50) NOT NULL,
                distance_km NUMERIC(10, 2) NOT NULL,
                carbon_saved_g NUMERIC(10, 2) NOT NULL,
                points_earned INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # 5. sos_contacts
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sos_contacts (
                id SERIAL PRIMARY KEY,
                user_email VARCHAR(255) REFERENCES users(email) ON DELETE CASCADE,
                contact_name VARCHAR(255) NOT NULL,
                phone_number VARCHAR(50) NOT NULL,
                relationship VARCHAR(50) NOT NULL
            );
        """)
        
        # 6. safety_reports
        cur.execute("""
            CREATE TABLE IF NOT EXISTS safety_reports (
                id SERIAL PRIMARY KEY,
                area VARCHAR(255) UNIQUE NOT NULL,
                lighting INTEGER NOT NULL CHECK (lighting >= 0 AND lighting <= 100),
                crowd INTEGER NOT NULL CHECK (crowd >= 0 AND crowd <= 100),
                crime INTEGER NOT NULL CHECK (crime >= 0 AND crime <= 100),
                safety_score INTEGER NOT NULL
            );
        """)
        
        # 7. carbon_logs
        cur.execute("""
            CREATE TABLE IF NOT EXISTS carbon_logs (
                id SERIAL PRIMARY KEY,
                user_email VARCHAR(255) REFERENCES users(email) ON DELETE CASCADE,
                mode VARCHAR(50) NOT NULL,
                distance_km NUMERIC(10, 2) NOT NULL,
                emissions_g NUMERIC(10, 2) NOT NULL,
                saved_g NUMERIC(10, 2) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 8. tnstc_routes
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tnstc_routes (
                id SERIAL PRIMARY KEY,
                bus_no VARCHAR(50) NOT NULL,
                stops JSONB NOT NULL,
                frequency_min INTEGER NOT NULL,
                travel_time_min INTEGER NOT NULL
            );
        """)

        # 9. trains
        cur.execute("""
            CREATE TABLE IF NOT EXISTS trains (
                id SERIAL PRIMARY KEY,
                number VARCHAR(50) UNIQUE NOT NULL,
                name VARCHAR(255) NOT NULL,
                origin VARCHAR(255) NOT NULL,
                destination VARCHAR(255) NOT NULL,
                departure VARCHAR(10) NOT NULL,
                arrival VARCHAR(10) NOT NULL,
                duration VARCHAR(50) NOT NULL,
                classes VARCHAR(50) NOT NULL,
                fare_sl INTEGER NOT NULL
            );
        """)

        # 10. sos_alerts
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sos_alerts (
                id SERIAL PRIMARY KEY,
                user_email VARCHAR(255) REFERENCES users(email) ON DELETE CASCADE,
                lat NUMERIC(10, 6) NOT NULL,
                lng NUMERIC(10, 6) NOT NULL,
                driver_name VARCHAR(255),
                driver_phone VARCHAR(50),
                vehicle_number VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        print("[SUCCESS] Database tables successfully created/checked.")
        seed_data(conn)
        cur.close()
        conn.close()
    except Exception as e:
        print(f"[ERROR] Error initializing database tables: {e}")
        raise


def seed_mock_db():
    print("[SEED] Seeding Mock database in memory...")
    MOCK_DB["users"] = {
        "demo@mobilityos.in": {"password": "demo1234", "name": "Gopi", "role": "user"},
        "admin@mobilityos.in": {"password": "admin123", "name": "Admin", "role": "admin"}
    }
    MOCK_DB["sos_contacts"]["demo@mobilityos.in"] = [
        {"id": 1, "contact_name": "Mother", "phone_number": "+91 98765 43210", "relationship": "Mother"},
        {"id": 2, "contact_name": "Father", "phone_number": "+91 87654 32109", "relationship": "Father"}
    ]
    seed_safety = [
        ("Gandhipuram", 90, 85, 15),
        ("Othakkalmandapam", 70, 60, 20),
        ("Karpagam College", 85, 75, 10),
        ("Eachanari", 75, 65, 12),
        ("Sundarapuram", 80, 70, 18),
        ("Ukkadam", 65, 90, 25),
        ("Coimbatore Junction", 88, 92, 14),
        ("Chennai Central", 90, 95, 18),
        ("Koyambedu", 70, 90, 22),
        ("Guindy", 85, 80, 15),
        ("Tambaram", 80, 85, 14),
        ("Madurai Junction", 82, 88, 20),
        ("Trichy Junction", 85, 82, 12),
        ("Salem Junction", 80, 78, 15),
        ("Tirunelveli Junction", 78, 75, 16),
        ("Vellore", 85, 80, 12),
        ("Erode", 80, 78, 14),
        ("Pollachi", 75, 70, 15),
        ("Ooty", 88, 80, 10)
    ]
    for name, lit, crd, crm in seed_safety:
        score = int(lit * 0.4 + crd * 0.4 + (100 - crm) * 0.2)
        MOCK_DB["safety_reports"][name.lower()] = {
            "area": name, "lighting": lit, "crowd": crd, "crime": crm, "safety_score": score
        }
    
    MOCK_DB["tnstc_routes"] = [
        {"id": 1, "bus_no": "33A", "stops": ["Othakkalmandapam", "Karpagam College", "Eachanari", "Sundarapuram", "Ukkadam", "Coimbatore Junction", "Gandhipuram"], "frequency_min": 10, "travel_time_min": 40},
        {"id": 2, "bus_no": "12B", "stops": ["Karpagam College", "Eachanari", "Ukkadam", "Gandhipuram"], "frequency_min": 15, "travel_time_min": 30},
        {"id": 3, "bus_no": "Express-101", "stops": ["Coimbatore Junction", "Erode", "Salem Junction", "Vellore", "Chennai Central"], "frequency_min": 60, "travel_time_min": 480},
        {"id": 4, "bus_no": "Express-202", "stops": ["Coimbatore Junction", "Pollachi", "Madurai Junction"], "frequency_min": 45, "travel_time_min": 180},
        {"id": 5, "bus_no": "Chennai-Local-1", "stops": ["Tambaram", "Guindy", "Koyambedu", "Chennai Central"], "frequency_min": 8, "travel_time_min": 45}
    ]

    MOCK_DB["trains"] = [
        {"id": 1, "number": "12674", "name": "Cheran Express", "origin": "Coimbatore Junction", "destination": "Chennai Central", "departure": "22:40", "arrival": "07:00", "duration": "8h 20m", "classes": "2A/3A/SL", "fare_sl": 310},
        {"id": 2, "number": "12680", "name": "Intercity Express", "origin": "Coimbatore Junction", "destination": "Chennai Central", "departure": "06:15", "arrival": "13:50", "duration": "7h 35m", "classes": "CC/2S", "fare_sl": 185},
        {"id": 3, "number": "12676", "name": "Kovai Express", "origin": "Coimbatore Junction", "destination": "Chennai Central", "departure": "15:15", "arrival": "22:50", "duration": "7h 35m", "classes": "CC/2S", "fare_sl": 185},
        {"id": 4, "number": "22669", "name": "Shatabdi Express", "origin": "Chennai Central", "destination": "Coimbatore Junction", "departure": "07:10", "arrival": "14:15", "duration": "7h 05m", "classes": "EC/CC", "fare_sl": 950},
        {"id": 5, "number": "12631", "name": "Nellai Express", "origin": "Chennai Central", "destination": "Tirunelveli Junction", "departure": "20:10", "arrival": "07:40", "duration": "11h 30m", "classes": "2A/3A/SL", "fare_sl": 385},
        {"id": 6, "number": "16101", "name": "Boat Mail", "origin": "Chennai Central", "destination": "Madurai Junction", "departure": "19:15", "origin_station": "Chennai", "arrival": "06:30", "duration": "11h 15m", "classes": "2A/3A/SL", "fare_sl": 340}
    ]
    MOCK_DB["reward_points"] = [
        {"user_email": "demo@mobilityos.in", "points": 2840, "reason": "Initial points"},
        {"user_email": "admin@mobilityos.in", "points": 500, "reason": "Initial points"}
    ]
    MOCK_DB["journeys"] = [
        {"user_email": "demo@mobilityos.in", "origin": "Karpagam College", "destination": "Chennai Central", "route_details": {"options": [{"label": "Fastest", "total_time_min": 520, "total_cost_inr": 360}]}, "created_at": "2026-06-15 10:00:00"},
        {"user_email": "demo@mobilityos.in", "origin": "Coimbatore", "destination": "Ukkadam", "route_details": {"options": [{"label": "Cheapest", "total_time_min": 15, "total_cost_inr": 15}]}, "created_at": "2026-06-15 11:30:00"}
    ]
    MOCK_DB["trip_history"] = [
        {"user_email": "demo@mobilityos.in", "origin": "Karpagam College", "destination": "Gandhipuram", "mode": "bus", "distance_km": 12.0, "carbon_saved_g": 1420, "points_earned": 14, "created_at": "2026-06-15 09:00:00"},
        {"user_email": "demo@mobilityos.in", "origin": "Othakkalmandapam", "destination": "Coimbatore Junction", "mode": "train", "distance_km": 18.0, "carbon_saved_g": 3200, "points_earned": 32, "created_at": "2026-06-15 08:30:00"}
    ]

# CRUD operations helpers (handles fallback transparently)
def db_query(query, params=(), fetchone=False, fetchall=False):
    conn = get_db_connection()
    if MOCK_MODE or not conn:
        return mock_query(query, params, fetchone, fetchall)
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(query, params)
        res = None
        if fetchone:
            res = cur.fetchone()
        elif fetchall:
            res = cur.fetchall()
        cur.close()
        conn.close()
        return res
    except Exception as e:
        print(f"[WARNING] DB Query Error: {e}")
        return None

def db_execute(query, params=(), commit=True):
    conn = get_db_connection()
    if MOCK_MODE or not conn:
        return mock_execute(query, params)
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        if commit:
            conn.commit()
        last_id = None
        try:
            last_id = cur.lastrowid
        except:
            pass
        cur.close()
        conn.close()
        return last_id or True
    except Exception as e:
        print(f"[WARNING] DB Execute Error: {e}")
        return False

# In-memory Mock DB operations
def mock_query(query, params, fetchone, fetchall):
    q_lower = query.lower()
    # Mocking standard queries we use
    if "select * from users where email =" in q_lower or "select email" in q_lower:
        email = params[0]
        u = MOCK_DB["users"].get(email)
        if u:
            return {"email": email, "password": u["password"], "name": u["name"], "role": u["role"]}
        return None
    elif "select count(*) from users" in q_lower:
        return [len(MOCK_DB["users"])] if fetchall else {"count": len(MOCK_DB["users"])}
    elif "select name, email, role from users" in q_lower or "select email, name, role from users" in q_lower or "select * from users" in q_lower:
        return [{"name": u["name"], "email": k, "role": u["role"]} for k, u in MOCK_DB["users"].items()]
    elif "select sum(carbon_saved_g)" in q_lower:
        total = sum(x["carbon_saved_g"] for x in MOCK_DB["trip_history"])
        return {"sum": total}
    elif "select count(*) from trip_history" in q_lower:
        return {"count": len(MOCK_DB["trip_history"])}
    elif "select sum(points) from reward_points" in q_lower or "select sum(points)" in q_lower:
        email = params[0]
        pts = sum(x["points"] for x in MOCK_DB["reward_points"] if x["user_email"] == email)
        return {"sum": pts}
    elif "select * from sos_contacts" in q_lower:
        email = params[0]
        return MOCK_DB["sos_contacts"].get(email, [])
    elif "select * from safety_reports where" in q_lower:
        area = params[0].lower()
        # substring search
        for k, v in MOCK_DB["safety_reports"].items():
            if k in area or area in k:
                return v
        return None
    elif "select * from safety_reports" in q_lower:
        return list(MOCK_DB["safety_reports"].values())
    elif "select * from tnstc_routes" in q_lower:
        return MOCK_DB["tnstc_routes"]
    elif "select * from trains where" in q_lower:
        origin, dest = params[0].lower(), params[1].lower()
        res = []
        for t in MOCK_DB["trains"]:
            if origin in t["origin"].lower() and dest in t["destination"].lower():
                res.append(t)
        return res
    elif "select * from sos_alerts" in q_lower:
        return MOCK_DB["sos_alerts"]
    elif "select * from trip_history order by" in q_lower or "select user_email, origin, destination, mode, distance_km" in q_lower:
        return MOCK_DB["trip_history"][-10:] if fetchone else MOCK_DB["trip_history"]
    elif "select user_email, origin, destination, route_details" in q_lower or "select * from journeys" in q_lower:
        return MOCK_DB["journeys"]
    return []

def mock_execute(query, params):
    q_lower = query.lower()
    if "insert into users" in q_lower:
        email, password, name, role = params[0], params[1], params[2], params[3]
        if email in MOCK_DB["users"]:
            return False
        MOCK_DB["users"][email] = {"password": password, "name": name, "role": role}
        return True
    elif "update users set name" in q_lower:
        name, email = params[0], params[1]
        if email in MOCK_DB["users"]:
            MOCK_DB["users"][email]["name"] = name
            return True
        return False
    elif "insert into sos_contacts" in q_lower:
        email, name, phone, rel = params[0], params[1], params[2], params[3]
        if email not in MOCK_DB["sos_contacts"]:
            MOCK_DB["sos_contacts"][email] = []
        new_id = len(MOCK_DB["sos_contacts"][email]) + 1
        MOCK_DB["sos_contacts"][email].append({
            "id": new_id, "user_email": email, "contact_name": name,
            "phone_number": phone, "relationship": rel
        })
        return True
    elif "delete from sos_contacts" in q_lower:
        cid, email = params[0], params[1]
        if email in MOCK_DB["sos_contacts"]:
            MOCK_DB["sos_contacts"][email] = [x for x in MOCK_DB["sos_contacts"][email] if x["id"] != cid]
        return True
    elif "insert into sos_alerts" in q_lower:
        email, lat, lng, d_name, d_phone, v_num = params[0], params[1], params[2], params[3], params[4], params[5]
        MOCK_DB["sos_alerts"].append({
            "id": len(MOCK_DB["sos_alerts"]) + 1, "user_email": email, "lat": lat, "lng": lng,
            "driver_name": d_name, "driver_phone": d_phone, "vehicle_number": v_num,
            "created_at": "2026-06-15 12:00:00"
        })
        return True
    elif "insert into reward_points" in q_lower:
        email, pts, reason = params[0], params[1], params[2]
        MOCK_DB["reward_points"].append({"user_email": email, "points": pts, "reason": reason})
        return True
    elif "insert into trip_history" in q_lower:
        email, o, d, m, dist, carb, pts = params[0], params[1], params[2], params[3], params[4], params[5], params[6]
        MOCK_DB["trip_history"].append({
            "user_email": email, "origin": o, "destination": d, "mode": m,
            "distance_km": dist, "carbon_saved_g": carb, "points_earned": pts,
            "created_at": "2026-06-15 12:00:00"
        })
        return True
    return True