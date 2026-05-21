import math
import threading
import requests
import random
from config import NOMINATIM_URL, OSRM_URL, GAME_CONFIG
from game.models import Treasure, rate_limit

def _haversine_m(a, b):
    R = 6371000
    r = math.pi / 180
    dlat = (b[0] - a[0]) * r
    dlon = (b[1] - a[1]) * r
    x = math.sin(dlat/2)**2 + math.cos(a[0]*r)*math.cos(b[0]*r)*math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(x), math.sqrt(1-x))

def _spread_select(elements, count):
    """Greedy spread selection — pick `count` POIs maximising minimum distance."""
    for min_d in [200, 150, 100, 60]:
        selected = []
        pool = list(elements)
        random.shuffle(pool)
        for e in pool:
            coord = (e["lat"], e["lon"])
            if all(_haversine_m(coord, (s["lat"], s["lon"])) >= min_d for s in selected):
                selected.append(e)
                if len(selected) >= count:
                    break
        if len(selected) >= count:
            return selected
    pool = list(elements); random.shuffle(pool)
    return pool[:count]

OVERPASS_MIRRORS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]

HEADERS = {"User-Agent": "TreasureHuntGame/1.0", "Accept": "*/*"}


def _parallel_post(query: str, handler, per_timeout: float, total_timeout: float):
    """
    POST query to all OVERPASS_MIRRORS simultaneously.
    Calls handler(resp_json) on first successful response.
    Returns handler result, or None if all fail / timeout.
    """
    result = [None]
    done = threading.Event()
    remaining = [len(OVERPASS_MIRRORS)]
    lock = threading.Lock()

    def try_url(url):
        try:
            resp = requests.post(url, data={"data": query}, headers=HEADERS,
                                 timeout=per_timeout)
            resp.raise_for_status()
            value = handler(resp.json())
            with lock:
                if not done.is_set():
                    result[0] = value
                    done.set()
        except Exception:
            pass
        finally:
            with lock:
                remaining[0] -= 1
                if remaining[0] == 0:
                    done.set()  # all mirrors failed

    for url in OVERPASS_MIRRORS:
        threading.Thread(target=try_url, args=(url,), daemon=True).start()

    done.wait(timeout=total_timeout)
    return result[0]


class MapAPI:
    _road_cache: dict = {}

    @staticmethod
    @rate_limit(calls_per_second=1)
    def geocode(city_name: str) -> dict:
        params = {"q": city_name, "format": "json", "limit": 1}
        resp = requests.get(f"{NOMINATIM_URL}/search", params=params,
                            headers=HEADERS, timeout=6)
        resp.raise_for_status()
        results = resp.json()
        if not results:
            raise ValueError(f"找不到城市: {city_name}")
        return {"lat": float(results[0]["lat"]), "lon": float(results[0]["lon"])}

    @staticmethod
    def _query_overpass(query: str) -> list:
        """並行查詢所有鏡像站，回傳第一個成功的結果。"""
        result = _parallel_post(
            query,
            handler=lambda j: j.get("elements", []),
            per_timeout=5,
            total_timeout=7,
        )
        if result is None:
            raise RuntimeError("All Overpass mirrors failed")
        return result

    @staticmethod
    def fetch_roads(lat: float, lon: float) -> dict:
        """備援：以起點為中心 900m 半徑查詢建築物（並行鏡像）。"""
        key = (round(lat, 2), round(lon, 2))
        if key in MapAPI._road_cache:
            return MapAPI._road_cache[key]

        d = 0.008
        query = (
            f"[out:json][timeout:12][maxsize:33554432];"
            f"way[\"building\"]({lat-d},{lon-d},{lat+d},{lon+d});"
            f"(._;>;);out body;"
        )
        result = _parallel_post(
            query,
            handler=MapAPI._parse_map_data,
            per_timeout=14,
            total_timeout=16,
        )
        if result is None:
            return {"roads": {"type": "FeatureCollection", "features": []}, "buildings": []}
        MapAPI._road_cache[key] = result
        return result

    @staticmethod
    def fetch_roads_focused(points: list, radius_deg: float = 0.0013) -> dict:
        """
        用 Overpass union 語法，一次查詢多個小 bbox（出發點＋各寶藏＋路線取樣點）。
        比全 bbox 少查 60–80% 面積，且只查玩家實際會走到的區域。
        """
        pts = points[:14]
        key = "fp_" + "_".join(f"{round(p[0],3)},{round(p[1],3)}" for p in pts)
        if key in MapAPI._road_cache:
            return MapAPI._road_cache[key]

        R = radius_deg
        clauses = "".join(
            f'way["building"]({p[0]-R:.5f},{p[1]-R:.5f},{p[0]+R:.5f},{p[1]+R:.5f});'
            for p in pts
        )
        query = (
            f"[out:json][timeout:20][maxsize:67108864];"
            f"({clauses})"
            f"(._;>;);out body;"
        )
        result = _parallel_post(
            query,
            handler=MapAPI._parse_map_data,
            per_timeout=22,
            total_timeout=24,
        )
        if result is None:
            result = {"roads": {"type": "FeatureCollection", "features": []}, "buildings": []}
        MapAPI._road_cache[key] = result
        return result

    @staticmethod
    def fetch_roads_bbox(s: float, n: float, w: float, e: float) -> dict:
        """主要建築物查詢：並行鏡像，最先回傳的鏡像獲勝。"""
        key = (round(s, 3), round(n, 3), round(w, 3), round(e, 3))
        if key in MapAPI._road_cache:
            return MapAPI._road_cache[key]

        query = (
            f"[out:json][timeout:20][maxsize:67108864];"
            f"way[\"building\"]({s},{w},{n},{e});"
            f"(._;>;);out body;"
        )
        result = _parallel_post(
            query,
            handler=MapAPI._parse_map_data,
            per_timeout=22,
            total_timeout=24,
        )
        if result is not None:
            MapAPI._road_cache[key] = result
            return result

        # 全 bbox 失敗 → 退回城市中心小範圍
        clat, clon = (s + n) / 2, (w + e) / 2
        fallback = MapAPI.fetch_roads(clat, clon)
        if fallback["buildings"]:
            MapAPI._road_cache[key] = fallback
        return fallback

    @staticmethod
    def _parse_map_data(data: dict) -> dict:
        nodes = {e["id"]: [e["lon"], e["lat"]]
                 for e in data.get("elements", []) if e["type"] == "node"}
        road_features, buildings = [], []
        for e in data.get("elements", []):
            if e["type"] != "way":
                continue
            tags = e.get("tags", {})
            coords = [nodes[n] for n in e.get("nodes", []) if n in nodes]
            if "highway" in tags and len(coords) >= 2:
                road_features.append({
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": coords},
                    "properties": {"hw": tags.get("highway", "")}
                })
            elif "building" in tags and len(coords) >= 4:
                try:
                    layer = int(tags.get("layer", 0) or 0)
                except (ValueError, TypeError):
                    layer = 0
                if (tags.get("bridge") or tags.get("man_made") == "bridge" or
                        tags.get("tunnel") or
                        tags.get("building") in ("bridge", "passage", "roof") or
                        layer >= 1 or layer < 0):
                    continue
                if len(coords) > 24:
                    step = max(1, len(coords) // 20)
                    coords = coords[::step]
                buildings.append(coords)
        return {
            "roads": {"type": "FeatureCollection", "features": road_features},
            "buildings": buildings[:3000]
        }

    @staticmethod
    def fetch_poi_all(lat: float, lon: float) -> list:
        """
        Return named POIs as {lat,lon,name,category}.
        1) Fast node-only Overpass query (no centroid computation).
        2) Nominatim keyword fallback if Overpass fully fails.
        """
        d = 0.015   # ±1670 m bbox
        bb = f"{lat-d},{lon-d},{lat+d},{lon+d}"
        # node-only: far lighter than nwr, no out center needed
        query = (
            f'[out:json][timeout:18];'
            f'(node["amenity"]["name"]({bb});'
            f' node["tourism"]["name"]({bb});'
            f' node["leisure"]["name"]({bb});'
            f' node["historic"]["name"]({bb});'
            f' node["natural"]["name"]({bb});'
            f');out body;'
        )
        els = _parallel_post(
            query,
            handler=lambda j: j.get("elements", []),
            per_timeout=20, total_timeout=22,
        ) or []

        result = []
        seen = set()
        for e in els:
            tags = e.get("tags", {})
            name = tags.get("name", "")
            if not name or name in seen:
                continue
            seen.add(name)
            category = (tags.get("tourism") or tags.get("historic") or
                        tags.get("natural") or tags.get("amenity") or
                        tags.get("leisure", "place"))
            result.append({"lat": e["lat"], "lon": e["lon"],
                           "name": name, "category": category})

        if not result:
            result = MapAPI._nominatim_poi_raw(lat, lon)
        return result

    @staticmethod
    def _nominatim_poi_raw(lat: float, lon: float) -> list:
        """Nominatim fallback — returns same dict format as fetch_poi_all."""
        import time as _t
        d = 0.015
        viewbox = f"{lon-d},{lat+d},{lon+d},{lat-d}"
        keywords = ["restaurant", "cafe", "museum", "park",
                    "school", "hotel", "temple", "library"]
        result = []
        seen = set()
        for kw in keywords:
            if len(result) >= 80:
                break
            try:
                params = {"q": kw, "format": "json", "limit": 15,
                          "viewbox": viewbox, "bounded": 1}
                r = requests.get(f"{NOMINATIM_URL}/search", params=params,
                                 headers=HEADERS, timeout=6)
                for item in r.json():
                    name = (item.get("name") or
                            item.get("display_name", "").split(",")[0].strip())
                    if not name or name in seen:
                        continue
                    seen.add(name)
                    result.append({
                        "lat": float(item["lat"]), "lon": float(item["lon"]),
                        "name": name, "category": item.get("type", "place"),
                    })
            except Exception:
                pass
            _t.sleep(1.1)   # Nominatim ToS: max 1 req/s
        return result

    @staticmethod
    def fetch_poi(lat: float, lon: float) -> list:
        d = 0.010
        queries = [
            f'[out:json][timeout:7];(node["amenity"="cafe"]({lat-d},{lon-d},{lat+d},{lon+d});node["tourism"="museum"]({lat-d},{lon-d},{lat+d},{lon+d});node["amenity"="library"]({lat-d},{lon-d},{lat+d},{lon+d}););out body;',
            f'[out:json][timeout:7];(node["leisure"="park"]({lat-d},{lon-d},{lat+d},{lon+d});node["amenity"="restaurant"]({lat-d},{lon-d},{lat+d},{lon+d}););out body;',
        ]

        elements = []
        for q in queries:
            try:
                elements += MapAPI._query_overpass(q)
                if len(elements) >= GAME_CONFIG["treasure_count"] * 10:
                    break
            except Exception:
                pass

        if not elements:
            return MapAPI._fetch_poi_nominatim(lat, lon)

        valid = [e for e in elements if "name" in e.get("tags", {})]
        count = min(GAME_CONFIG["treasure_count"], len(valid))
        if count == 0:
            return MapAPI._fetch_poi_nominatim(lat, lon)

        selected = _spread_select(valid, count)
        treasures = []
        for i, poi in enumerate(selected):
            tags = poi.get("tags", {})
            category = tags.get("amenity") or tags.get("tourism") or tags.get("leisure", "place")
            treasures.append(Treasure(
                id=f"t{i}",
                name=tags.get("name", f"神秘地點 {i+1}"),
                lat=poi["lat"],
                lon=poi["lon"],
                category=category,
                points=100
            ))
        return treasures

    @staticmethod
    @rate_limit(calls_per_second=1)
    def _fetch_poi_nominatim(lat: float, lon: float) -> list:
        keywords = ["cafe", "museum", "park", "restaurant", "library"]
        results = []
        for kw in keywords:
            if len(results) >= GAME_CONFIG["treasure_count"]:
                break
            try:
                params = {
                    "q": kw, "format": "json", "limit": 3,
                    "viewbox": f"{lon-0.05},{lat+0.05},{lon+0.05},{lat-0.05}",
                    "bounded": 1
                }
                resp = requests.get(f"{NOMINATIM_URL}/search", params=params,
                                    headers=HEADERS, timeout=5)
                for r in resp.json():
                    if r.get("display_name") and len(results) < GAME_CONFIG["treasure_count"]:
                        results.append(r)
            except Exception:
                continue

        if not results:
            raise ValueError("無法取得周邊地點，請換一個城市試試")

        treasures = []
        for i, r in enumerate(results[:GAME_CONFIG["treasure_count"]]):
            name = r.get("name") or r["display_name"].split(",")[0]
            category = r.get("type", "place")
            treasures.append(Treasure(
                id=f"t{i}", name=name,
                lat=float(r["lat"]), lon=float(r["lon"]),
                category=category, points=100
            ))
        return treasures

    @staticmethod
    def get_route(coords: list) -> list:
        coord_str = ";".join(f"{lon},{lat}" for lat, lon in coords)
        url = f"{OSRM_URL}/route/v1/walking/{coord_str}"
        params = {"overview": "full", "geometries": "geojson"}
        try:
            resp = requests.get(url, params=params, timeout=8)
            resp.raise_for_status()
            return resp.json()["routes"][0]["geometry"]["coordinates"]
        except Exception:
            return []
