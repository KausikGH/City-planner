from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from geopy.distance import geodesic
import requests
import logging

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

class CityPlannerAI:
    def __init__(self):
        self.rules = [
            {
                "condition": lambda f: f['amenities'] >= 3 and f['road_dist'] <= 50,
                "recommendation": "Mixed-use Development",
                "reason": "High commercial potential with good transport access"
            },
            {
                "condition": lambda f: f['area'] > 2000,
                "recommendation": "Public Park",
                "reason": "Large space suitable for green infrastructure"
            },
            {
                "condition": lambda _: True,
                "recommendation": "Residential Housing",
                "reason": "General urban expansion needs"
            }
        ]
    
    def analyze(self, features):
        for rule in self.rules:
            if rule["condition"](features):
                return rule

ai_engine = CityPlannerAI()

def get_osm_data(lat: float, lng: float, radius: int = 100):
    """Enhanced query for land use, buildings, and roads"""
    query = f"""
    [out:json];
    (
        way[building](around:{radius},{lat},{lng});
        way[landuse](around:{radius},{lat},{lng});
        way[highway](around:{radius},{lat},{lng});
        node[amenity](around:{radius},{lat},{lng});
    );
    out body;
    >;
    out skel qt;
    """
        response = requests.post(OVERPASS_URL, data=query, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"OSM API Error: {str(e)}")
        raise HTTPException(500, "Map data service error")
def calculate_features(lat: float, lng: float):
    data = get_osm_data(lat, lng)
    
    # Check land use (agricultural, residential, etc.)
    land_use = next((
        element.get('tags', {}).get('landuse')
        for element in data.get('elements', [])
        if element.get('type') == 'way' and 'landuse' in element.get('tags', {})
    ), None)
    
    has_buildings = any(
        element.get('type') == 'way' and 'building' in element.get('tags', {})
        for element in data.get('elements', [])
    )

    amenities = sum(
        1 for element in data.get('elements', [])
        if element.get('type') == 'node' and 'amenity' in element.get('tags', {})
    )

    roads = [
        element for element in data.get('elements', [])
        if element.get('type') == 'way' and 'highway' in element.get('tags', {})
    ]
    
    min_road_dist = 300
    if roads:
        try:
            min_road_dist = min(
                geodesic((lat, lng), (node['lat'], node['lon'])).meters
                for road in roads
                for node in road.get('nodes', [])
                if 'lat' in node and 'lon' in node
            )
        except ValueError:
            pass
    return {
        "is_empty": not has_buildings,
        "land_use": land_use,
        "area": 1500,
        "amenities": amenities,
        "road_dist": min_road_dist
    }

@app.get("/recommend")
async def get_recommendation(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180)  # Changed from 'lon' to 'lng'
):
    try:
        features = calculate_features(lat, lng)
        
        if not features["is_empty"]:
            return {"error": "Selected area contains existing buildings"}
        
        recommendation = ai_engine.analyze(features)
        
        return {
            "status": "success",
            "location": {"lat": lat, "lng": lng},  # Changed key from 'lon' to 'lng'
            "analysis": {
                "area_m2": features["area"],
                "amenities_count": features["amenities"],
                "road_distance_m": features["road_dist"]
            },
            "recommendation": {
                "type": recommendation["recommendation"],
                "reason": recommendation["reason"]
            }
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"System error: {str(e)}")
        raise HTTPException(500, "Analysis failed")

@app.get("/test")
def test_endpoint():
    return {"status": "Backend operational"}