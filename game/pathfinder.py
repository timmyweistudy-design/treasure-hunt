import math
from itertools import permutations
from typing import List, Tuple


def haversine(coord1: Tuple, coord2: Tuple) -> float:
    R = 6371000
    lat1, lon1 = math.radians(coord1[0]), math.radians(coord1[1])
    lat2, lon2 = math.radians(coord2[0]), math.radians(coord2[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))


def solve_tsp_nearest_neighbor(start: Tuple, treasures: List) -> List:
    if not treasures:
        return []
    unvisited = list(range(len(treasures)))
    route = []
    current = start
    while unvisited:
        nearest_idx = min(unvisited, key=lambda i: haversine(current, treasures[i].coords))
        route.append(treasures[nearest_idx])
        current = treasures[nearest_idx].coords
        unvisited.remove(nearest_idx)
    return route


def solve_tsp_exact(start: Tuple, treasures: List) -> List:
    if len(treasures) > 8:
        return solve_tsp_nearest_neighbor(start, treasures)
    if not treasures:
        return []
    best_route, best_dist = None, float("inf")
    for perm in permutations(range(len(treasures))):
        dist = haversine(start, treasures[perm[0]].coords)
        for i in range(len(perm) - 1):
            dist += haversine(treasures[perm[i]].coords, treasures[perm[i+1]].coords)
        if dist < best_dist:
            best_dist = dist
            best_route = [treasures[i] for i in perm]
    return best_route or []


def calculate_total_distance(start: Tuple, route: List) -> float:
    if not route:
        return 0
    coords = [start] + [t.coords for t in route]
    return sum(haversine(coords[i], coords[i+1]) for i in range(len(coords)-1))
