# mauzenfan/server/api_app./geo_utils.py
import math

def calculate_haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance in meters between two points
    on the earth (specified in decimal degrees) using Haversine formula.
    """
    # Radius of earth in kilometers
    R = 6371.0

    # Convert decimal degrees to radians
    # Ensure inputs are explicitly cast to float for safety if they are Decimal or string
    lat1_rad = math.radians(float(lat1))
    lon1_rad = math.radians(float(lon1))
    lat2_rad = math.radians(float(lat2))
    lon2_rad = math.radians(float(lon2))

    # Haversine formula
    dlon = lon2_rad - lon1_rad
    dlat = lat2_rad - lat1_rad

    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    distance_km = R * c
    distance_m = distance_km * 1000

    return distance_m

# Example usage (can be commented out or removed)
# if __name__ == '__main__':
#     # Example coordinates (e.g., Eiffel Tower to Louvre Museum)
#     lat1_et, lon1_et = 48.8584, 2.2945
#     lat2_lm, lon2_lm = 48.8606, 2.3376
#     distance = calculate_haversine_distance(lat1_et, lon1_et, lat2_lm, lon2_lm)
#     print(f"Distance: {distance:.2f} meters")
