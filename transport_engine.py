import math
import json

from polars import duration
from requests import options
from database import db_query

class TrainProvider:
    """Interface for Train schedules - easy to swap with real live APIs later."""
    def get_trains(self, origin: str, destination: str):
        raise NotImplementedError

class MockTrainProvider(TrainProvider):
    def get_trains(self, origin: str, destination: str):
        # Query trains table
        trains = db_query(
            "SELECT * FROM trains WHERE LOWER(origin) LIKE %s AND LOWER(destination) LIKE %s;",
            (f"%{origin.lower()}%", f"%{destination.lower()}%"),
            fetchall=True
        )
        # If DB query failed or empty, fallback to hardcoded list
        if not trains:
            from database import MOCK_MODE, MOCK_DB
            if MOCK_MODE:
                res = []
                for t in MOCK_DB["trains"]:
                    if origin.lower() in t["origin"].lower() and destination.lower() in t["destination"].lower():
                        res.append(t)
                return res
        return trains

# Simple helper for Haversine distance
def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0  # Earth radius in km
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

class TransportGraphEngine:
    def __init__(self):
        self.train_provider = MockTrainProvider()
        # Seed coordinates for major nodes/stops
        self.nodes = {
            "Karpagam College": {"lat": 10.9022, "lng": 76.9628, "type": "bus_stop", "area": "Karpagam College"},
            "Othakkalmandapam": {"lat": 10.8872, "lng": 76.9585, "type": "bus_stop", "area": "Othakkalmandapam"},
            "Eachanari": {"lat": 10.9184, "lng": 76.9691, "type": "bus_stop", "area": "Eachanari"},
            "Sundarapuram": {"lat": 10.9526, "lng": 76.9745, "type": "bus_stop", "area": "Sundarapuram"},
            "Ukkadam": {"lat": 10.9870, "lng": 76.9620, "type": "bus_stop", "area": "Ukkadam"},
            "Coimbatore Junction": {"lat": 11.0001, "lng": 76.9669, "type": "railway_station", "area": "Coimbatore Junction"},
            "Gandhipuram": {"lat": 11.0182, "lng": 76.9715, "type": "bus_stop", "area": "Gandhipuram"},
            "Chennai Central": {"lat": 13.0827, "lng": 80.2707, "type": "railway_station", "area": "Chennai Central"},
            "Koyambedu": {"lat": 13.0694, "lng": 80.2078, "type": "bus_stop", "area": "Koyambedu"},
            "Guindy": {"lat": 13.0067, "lng": 80.2206, "type": "bus_stop", "area": "Guindy"},
            "Tambaram": {"lat": 12.9249, "lng": 80.1462, "type": "bus_stop", "area": "Tambaram"},
            "Madurai Junction": {"lat": 9.9197, "lng": 78.1102, "type": "railway_station", "area": "Madurai Junction"},
            "Trichy Junction": {"lat": 10.7850, "lng": 78.6830, "type": "railway_station", "area": "Trichy Junction"},
            "Salem Junction": {"lat": 11.6680, "lng": 78.1180, "type": "railway_station", "area": "Salem Junction"},
            "Pollachi": {"lat": 10.6588, "lng": 77.0076, "type": "bus_stop", "area": "Pollachi"},
            "Ooty": {"lat": 11.4102, "lng": 76.6950, "type": "bus_stop", "area": "Ooty"}
        }

    def get_nearest_node(self, lat: float, lng: float, node_type: str = None):
        """Finds closest node in coordinate map."""
        min_dist = float('inf')
        nearest_name = None
        for name, data in self.nodes.items():
            if node_type and data["type"] != node_type:
                continue
            dist = haversine(lat, lng, data["lat"], data["lng"])
            if dist < min_dist:
                min_dist = dist
                nearest_name = name
        return nearest_name, min_dist

    def get_safety_score(self, area: str):
        """Calculates area safety score from database."""
        row = db_query("SELECT lighting, crowd, crime FROM safety_reports WHERE LOWER(area) = LOWER(%s);", (area,))
        if row:
            # Score formula: lighting*40% + crowd*40% + (100-crime)*20%
            return int(row["lighting"] * 0.4 + row["crowd"] * 0.4 + (100 - row["crime"]) * 0.2)
        # Default safety score if area not found
        return 75

    def get_carbon_saved(self, mode: str, dist_km: float):
        """Calculates CO2 saved in grams vs single occupancy car (192 g/km)."""
        factors = {
            "train": 14, "metro": 10, "bus": 68, "auto": 150,
            "electric_auto": 40, "walk": 0, "cycle": 0, "cab": 180, "bike": 110
        }
        factor = factors.get(mode.lower(), 100)
        emissions = factor * dist_km
        car_baseline = 192 * dist_km
        return max(0.0, car_baseline - emissions)

    def plan_route(self, origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float, origin_name: str, dest_name: str):
        """Builds multi-modal options based on distances and available transit, recommending all modes."""
        total_dist = haversine(origin_lat, origin_lng, dest_lat, dest_lng)
        
        # Identify nearest stops/stations
        near_bus_origin, bus_dist_origin = self.get_nearest_node(origin_lat, origin_lng, "bus_stop")
        near_train_origin, train_dist_origin = self.get_nearest_node(origin_lat, origin_lng, "railway_station")
        near_bus_dest, bus_dist_dest = self.get_nearest_node(dest_lat, dest_lng, "bus_stop")
        near_train_dest, train_dist_dest = self.get_nearest_node(dest_lat, dest_lng, "railway_station")

        # If origin & dest names match exact nodes, override distance to 0
        if origin_name in self.nodes:
            near_bus_origin = origin_name
            bus_dist_origin = 0
            if self.nodes[origin_name]["type"] == "railway_station":
                near_train_origin = origin_name
                train_dist_origin = 0
        if dest_name in self.nodes:
            near_bus_dest = dest_name
            bus_dist_dest = 0
            if self.nodes[dest_name]["type"] == "railway_station":
                near_train_dest = dest_name
                train_dist_dest = 0

        options = []

        # Check for long-distance train route
        is_long_distance = total_dist > 50
        available_trains = []
        if is_long_distance:
            available_trains = self.train_provider.get_trains(near_train_origin, near_train_dest)

        if is_long_distance:
            # -------------------------------------------------------------
            # OPTION 1: Fastest (Direct Cab) - Road direct trip
            # -------------------------------------------------------------
            opt1_legs = [{
                "mode": "cab", "from": origin_name, "to": dest_name,
                "duration_min": int(total_dist * 1.1 + 15), "cost_inr": int(total_dist * 18 + 50),
                "distance_km": round(total_dist, 1), "safety_score": self.get_safety_score(dest_name)
            }]
            options.append(self._compile_option("Fastest", opt1_legs))

            # -------------------------------------------------------------
            # OPTION 2: Cheapest (Direct Bus / SETC or TNSTC Bus)
            # -------------------------------------------------------------
            # -------------------------------------------------------------
            # Multiple Bus Recommendations
            # -------------------------------------------------------------
            bus_types = [
                ("TNSTC Express", 1.5),
                ("SETC Ultra Deluxe", 1.8),
                ("AC Sleeper", 2.2),
                ("Volvo AC", 2.5)
            ]

            cheapest_bus_legs = None
            for bus_name, multiplier in bus_types:
                bus_legs = [{
                    "mode": "bus",
                    "from": origin_name,
                    "to": dest_name,
                    "duration_min": int(total_dist * 1.4 + 30),
                    "cost_inr": int(total_dist * multiplier + 20),
                    "distance_km": round(total_dist, 1),
                    "safety_score": self.get_safety_score(dest_name),
                    "bus_name": bus_name
                }]

                options.append(
                    self._compile_option(
                        f"Bus - {bus_name}",
                        bus_legs
                    )
                )
                if cheapest_bus_legs is None:
                    cheapest_bus_legs = bus_legs

            if cheapest_bus_legs:
                options.append(self._compile_option("Cheapest", cheapest_bus_legs))

            # -------------------------------------------------------------
            # OPTION 3: Eco-friendly (Multi-modal Train + Auto/Metro transfers)
            # -------------------------------------------------------------
            opt3_legs = []
            if available_trains:
                train = available_trains[10] if len(available_trains) > 10 else available_trains[0]
                # First leg: Auto to train station
                if train_dist_origin > 0.5:
                    opt3_legs.append({
                        "mode": "electric_auto", "from": origin_name, "to": near_train_origin,
                        "duration_min": int(train_dist_origin * 2.8 + 5), "cost_inr": int(train_dist_origin * 12 + 25),
                        "distance_km": round(train_dist_origin, 1), "safety_score": self.get_safety_score(near_train_origin)
                    })
                # Second leg: Train
                duration = ""
                if isinstance(train, dict):
                    duration = str(train.get("duration", ""))
                elif isinstance(train, (list, tuple)) and len(train) > 2:
                    duration = str(train[2])

                train_time = 480 if "8h" in duration else 450
                opt3_legs.append({
                    "mode": "train", "from": near_train_origin, "to": near_train_dest,
                    "duration_min": train_time, "cost_inr": train["fare_sl"],
                    "distance_km": round(total_dist - 20, 1), "safety_score": self.get_safety_score(near_train_dest)
                })
                # Third leg: Metro/Walk to dest
                if train_dist_dest > 0.5:
                    mode = "metro" if "chennai" in dest_name.lower() or "chennai" in near_train_dest.lower() else "walk"
                    opt3_legs.append({
                        "mode": mode, "from": near_train_dest, "to": dest_name,
                        "duration_min": int(train_dist_dest * 4.0 if mode == "metro" else train_dist_dest * 12),
                        "cost_inr": int(train_dist_dest * 2.0 + 10 if mode == "metro" else 0),
                        "distance_km": round(train_dist_dest, 1), "safety_score": self.get_safety_score(dest_name)
                    })
            else:
                # If no trains available, fallback to electric auto/bus direct
                opt3_legs.append({
                    "mode": "electric_auto", "from": origin_name, "to": dest_name,
                    "duration_min": int(total_dist * 1.3 + 20), "cost_inr": int(total_dist * 10 + 30),
                    "distance_km": round(total_dist, 1), "safety_score": self.get_safety_score(dest_name)
                })
            options.append(self._compile_option("Eco-friendly", opt3_legs))

        else:
            # Short distance journey recommendations
            # OPTION 1: Fastest (Direct Auto/Cab)
            opt1_legs = [{
                "mode": "cab" if total_dist > 8 else "auto", "from": origin_name, "to": dest_name,
                "duration_min": int(total_dist * 2.0 + 5), "cost_inr": int(total_dist * 15 + 30),
                "distance_km": round(total_dist, 1), "safety_score": self.get_safety_score(dest_name)
            }]
            options.append(self._compile_option("Fastest", opt1_legs))

            # OPTION 2: Cheapest (Direct Bus or Walk)
            opt2_legs = []
            if bus_dist_origin > 0.2:
                opt2_legs.append({
                    "mode": "walk", "from": origin_name, "to": near_bus_origin,
                    "duration_min": int(bus_dist_origin * 12), "cost_inr": 0,
                    "distance_km": round(bus_dist_origin, 1), "safety_score": self.get_safety_score(near_bus_origin)
                })
            opt2_legs.append({
                "mode": "bus", "from": near_bus_origin, "to": near_bus_dest,
                "duration_min": int(total_dist * 3.0 + 8), "cost_inr": int(total_dist * 1.2 + 10),
                "distance_km": round(total_dist, 1), "safety_score": self.get_safety_score(near_bus_dest)
            })
            if bus_dist_dest > 0.2:
                opt2_legs.append({
                    "mode": "walk", "from": near_bus_dest, "to": dest_name,
                    "duration_min": int(bus_dist_dest * 12), "cost_inr": 0,
                    "distance_km": round(bus_dist_dest, 1), "safety_score": self.get_safety_score(dest_name)
                })
            options.append(self._compile_option("Cheapest", opt2_legs))

            # OPTION 3: Eco-friendly (Electric Auto, Bike, or Walk)
            opt3_legs = []
            if total_dist > 3.0:
                opt3_legs.append({
                    "mode": "electric_auto", "from": origin_name, "to": dest_name,
                    "duration_min": int(total_dist * 2.8 + 5), "cost_inr": int(total_dist * 12 + 25),
                    "distance_km": round(total_dist, 1), "safety_score": self.get_safety_score(dest_name)
                })
            else:
                opt3_legs.append({
                    "mode": "walk", "from": origin_name, "to": dest_name,
                    "duration_min": int(total_dist * 12), "cost_inr": 0,
                    "distance_km": round(total_dist, 1), "safety_score": self.get_safety_score(dest_name)
                })
            options.append(self._compile_option("Eco-friendly", opt3_legs))

        return {
            "origin": origin_name,
            "destination": dest_name,
            "options": options
        }

    def _compile_option(self, label: str, legs: list):
        total_time = sum(l["duration_min"] for l in legs)
        total_cost = sum(l["cost_inr"] for l in legs)
        avg_safety = int(sum(l["safety_score"] for l in legs) / len(legs)) if legs else 75
        
        carbon_saved = 0.0
        for l in legs:
            carbon_saved += self.get_carbon_saved(l["mode"], l["distance_km"])
            
        return {
            "label": label,
            "legs": legs,
            "total_time_min": total_time,
            "total_cost_inr": total_cost,
            "carbon_g": round(carbon_saved),
            "safety_score": avg_safety
        }