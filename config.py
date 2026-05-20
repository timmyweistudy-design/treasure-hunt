NOMINATIM_URL = "https://nominatim.openstreetmap.org"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OSRM_URL = "https://router.project-osrm.org"

GAME_CONFIG = {
    "time_limit": 600,          # 10 分鐘
    "treasure_count": 20,
    "search_radius": 2000,
    "collect_radius": 50,           # 收集範圍（公尺），WASD 走到附近才能收集
    "time_bonus_rate": 1,           # 每剩1秒加幾分（最多 600*1=600 加分）
    "categories": ["cafe", "museum", "park", "library", "restaurant"]
}
