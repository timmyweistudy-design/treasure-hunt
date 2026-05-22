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


def _two_opt(start: Tuple, route: List) -> List:
    """2-opt local search: swap pairs of edges until no improvement found."""
    if len(route) < 3:
        return route
    best = list(route)
    n = len(best)
    improved = True
    while improved:
        improved = False
        for i in range(n - 1):
            pre = start if i == 0 else best[i - 1].coords
            ci  = best[i].coords
            for j in range(i + 2, n):
                cj   = best[j].coords
                post = best[j + 1].coords if j + 1 < n else None
                d_before = haversine(pre, ci) + (haversine(cj, post) if post else 0)
                d_after  = haversine(pre, cj) + (haversine(ci, post) if post else 0)
                if d_after < d_before - 0.5:       # 0.5 m 容差避免浮點數死循環
                    best[i:j + 1] = best[i:j + 1][::-1]
                    improved = True
                    break
            if improved:
                break
    return best


def solve_tsp_exact(start: Tuple, treasures: List) -> List:
    if len(treasures) > 8:
        route = solve_tsp_nearest_neighbor(start, treasures)
        return _two_opt(start, route)          # 2-opt 改善 greedy 結果
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
