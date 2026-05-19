import threading
import requests
import random
from config import NOMINATIM_URL, OSRM_URL, GAME_CONFIG
from game.models import Treasure, rate_limit

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
                            headers=HEADERS, timeout=10)
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
            per_timeout=6,
            total_timeout=9,
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
                if len(elements) >= GAME_CONFIG["treasure_count"] * 4:
                    break
            except Exception:
                pass

        if not elements:
            return MapAPI._fetch_poi_nominatim(lat, lon)

        valid = [e for e in elements if "name" in e.get("tags", {})]
        count = min(GAME_CONFIG["treasure_count"], len(valid))
        if count == 0:
            return MapAPI._fetch_poi_nominatim(lat, lon)

        selected = random.sample(valid, count)
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
