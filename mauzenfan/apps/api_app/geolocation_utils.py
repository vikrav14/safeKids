# mauzenfan/server/api_app/geolocation_utils.py
import math
import statistics # Added for potential use, though not strictly in the provided functions

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

def get_closest_point_on_path(point_lat, point_lon, path_points):
    """
    Finds the closest point (vertex) in path_points to the given point_lat, point_lon.
    path_points: list of [lat, lon] coordinates.
    Returns: A tuple (closest_point, min_distance_meters).
             (None, float('inf')) if path_points is empty.
    """
    if not path_points:
        return None, float('inf')

    min_dist_meters = float('inf')
    closest_point_on_path = None

    for p_path_lat, p_path_lon in path_points:
        # Calculate actual haversine distance to each vertex
        dist_meters = distance_in_meters(point_lat, point_lon, p_path_lat, p_path_lon)
        if dist_meters < min_dist_meters:
            min_dist_meters = dist_meters
            closest_point_on_path = (p_path_lat, p_path_lon)

    return closest_point_on_path, min_dist_meters

def calculate_average_distance_to_path(trip_points_coords, routine_path_coords):
    """
    Calculates the average distance from each point in trip_points_coords
    to the closest point (vertex) in routine_path_coords.
    trip_points_coords: list of [lat, lon]
    routine_path_coords: list of [lat, lon] representing the learned routine path
    Returns average distance in meters. Returns float('inf') if inputs are invalid or no valid points.
    """
    if not trip_points_coords or not routine_path_coords:
        return float('inf')

    total_distance = 0
    valid_points_count = 0

    for trip_lat, trip_lon in trip_points_coords:
        _, min_dist_to_routine_vertex = get_closest_point_on_path(trip_lat, trip_lon, routine_path_coords)

        if min_dist_to_routine_vertex != float('inf'):
            total_distance += min_dist_to_routine_vertex
            valid_points_count += 1

    if valid_points_count == 0:
        return float('inf') # Avoid division by zero if no points could be compared

    return total_distance / valid_points_count


# Example usage (optional, can be removed or kept for testing)
# if __name__ == '__main__':
#     # Eiffel Tower to Notre Dame Cathedral (approximate coordinates)
#     lat1_et, lon1_et = 48.8584, 2.2945
#     lat2_nd, lon2_nd = 48.8530, 2.3499

#     dist_km = haversine_distance(lat1_et, lon1_et, lat2_nd, lon2_nd)
#     dist_m = distance_in_meters(lat1_et, lon1_et, lat2_nd, lon2_nd)

#     print(f"Distance: {dist_km:.2f} km")
#     print(f"Distance: {dist_m:.2f} m")

#     path = [[48.8600, 2.3300], [48.8610, 2.3350], [48.8620, 2.3390]]
#     point = [48.8605, 2.3345]
#     closest_p, min_d = get_closest_point_on_path(point[0], point[1], path)
#     print(f"Closest point to {point} in path is {closest_p} with distance {min_d:.2f}m")

#     trip = [[48.8603, 2.3340], [48.8608, 2.3348], [48.8615, 2.3360]]
#     avg_dist = calculate_average_distance_to_path(trip, path)
#     print(f"Average distance from trip to path: {avg_dist:.2f}m")
