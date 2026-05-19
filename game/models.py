import time
import json
from dataclasses import dataclass, field
from typing import List
from functools import wraps


def rate_limit(calls_per_second=1):
    min_interval = 1.0 / calls_per_second
    last_called = [0.0]

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            elapsed = time.time() - last_called[0]
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
            result = func(*args, **kwargs)
            last_called[0] = time.time()
            return result
        return wrapper
    return decorator


def log_action(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        result = func(self, *args, **kwargs)
        print(f"[LOG] {self.name} 執行 {func.__name__} | 分數: {self.score}")
        return result
    return wrapper


@dataclass
class Treasure:
    id: str
    name: str
    lat: float
    lon: float
    category: str
    points: int = 100
    found: bool = False

    @property
    def coords(self):
        return (self.lat, self.lon)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "lat": self.lat,
            "lon": self.lon,
            "category": self.category,
            "points": self.points,
            "found": self.found
        }


@dataclass
class Player:
    name: str
    lat: float
    lon: float
    score: int = 0
    found_treasures: List[str] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)

    @property
    def coords(self):
        return (self.lat, self.lon)

    @property
    def elapsed_time(self):
        return time.time() - self.start_time

    @log_action
    def collect_treasure(self, treasure: 'Treasure'):
        if not treasure.found:
            treasure.found = True
            self.found_treasures.append(treasure.id)
            self.score += treasure.points

    def to_dict(self):
        return {
            "name": self.name,
            "score": self.score,
            "found": len(self.found_treasures),
            "time": round(self.elapsed_time, 1)
        }


class Scoreboard:
    def __init__(self, filepath="data/scores.json"):
        self.filepath = filepath
        self.scores = self._load()

    def _load(self):
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def save_score(self, player: Player, city: str = ""):
        entry = {
            "name": player.name,
            "score": player.score,
            "treasures": len(player.found_treasures),
            "time": round(player.elapsed_time, 1),
            "date": time.strftime("%Y-%m-%d"),
            "city": city
        }
        self.scores.append(entry)
        self.scores.sort(key=lambda x: (-x["score"], x["time"]))
        self.scores = self.scores[:100]
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(self.scores, f, ensure_ascii=False, indent=2)

    def get_top10(self, city: str = None):
        if city:
            filtered = [s for s in self.scores if s.get("city", "").lower() == city.lower()]
            return filtered[:10]
        return self.scores[:10]
