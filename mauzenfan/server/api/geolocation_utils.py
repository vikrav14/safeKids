# mauzenfan/server/api/geolocation_utils.py
import math

def haversine_distance(lat1, lon1, lat2, lon2, earth_radius_km=6371.0):
    """
    Calculate the distance between two points on Earth (specified in decimal degrees)
    using the Haversine formula. Result is in kilometers.
    """
    # Convert decimal degrees to radians
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    # Haversine formula
    dlon = lon2_rad - lon1_rad
    dlat = lat2_rad - lat1_rad

    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    distance_km = earth_radius_km * c
    return distance_km

def distance_in_meters(lat1, lon1, lat2, lon2):
    """
    Calculates distance and returns it in meters.
    Latitude and longitude should be in decimal degrees.
    Ensures inputs are float, as they might come from Django Decimal fields.
    """
    return haversine_distance(float(lat1), float(lon1), float(lat2), float(lon2)) * 1000.0

# Example usage (optional, can be removed or kept for testing)
# if __name__ == '__main__':
#     # Eiffel Tower to Notre Dame Cathedral (approximate coordinates)
#     lat1_et, lon1_et = 48.8584, 2.2945
#     lat2_nd, lon2_nd = 48.8530, 2.3499

#     dist_km = haversine_distance(lat1_et, lon1_et, lat2_nd, lon2_nd)
#     dist_m = distance_in_meters(lat1_et, lon1_et, lat2_nd, lon2_nd)

#     print(f"Distance: {dist_km:.2f} km")
#     print(f"Distance: {dist_m:.2f} m")
#     # Expected output around 4.11 km or 4110 m
