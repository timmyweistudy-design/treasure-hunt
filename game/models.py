import base64
import json
import os
import time
from dataclasses import dataclass, field
from functools import wraps
from typing import List


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

    def to_dict(self):
        return {
            "name": self.name,
            "score": self.score,
            "found": len(self.found_treasures),
            "time": round(self.elapsed_time, 1)
        }


_GH_TOKEN  = os.environ.get("GITHUB_TOKEN", "")
_GH_REPO   = "timmyweistudy-design/treasure-hunt"
_GH_FILE   = "scores.json"
_GH_API    = f"https://api.github.com/repos/{_GH_REPO}/contents/{_GH_FILE}"
_GH_HEADS  = {"Authorization": f"token {_GH_TOKEN}", "Content-Type": "application/json"}


def _gh_load():
    """從 GitHub 讀取排行榜，失敗回傳 None。"""
    if not _GH_TOKEN:
        return None
    try:
        import requests
        r = requests.get(_GH_API, headers=_GH_HEADS, timeout=5)
        if r.status_code != 200:
            return None
        data = r.json()
        return json.loads(base64.b64decode(data["content"]).decode()), data["sha"]
    except Exception:
        return None


def _gh_save(scores, sha):
    """把排行榜寫回 GitHub，失敗靜默。"""
    if not _GH_TOKEN:
        return
    try:
        import requests
        content = base64.b64encode(
            json.dumps(scores, ensure_ascii=False, indent=2).encode()
        ).decode()
        requests.put(_GH_API, headers=_GH_HEADS, timeout=8, json={
            "message": "update scores",
            "content": content,
            "sha": sha,
        })
    except Exception:
        pass


class Scoreboard:
    def __init__(self, filepath="data/scores.json"):
        self.filepath = filepath
        self._sha = None
        self.scores = self._load()

    def _load(self):
        result = _gh_load()
        if result is not None:
            scores, self._sha = result
            return scores
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
        # 先嘗試 GitHub，再本機備份
        if self._sha:
            _gh_save(self.scores, self._sha)
            # 重新讀 SHA 以便下次寫入
            result = _gh_load()
            if result:
                _, self._sha = result
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.scores, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get_top10(self, city: str = None):
        if city:
            filtered = [s for s in self.scores if s.get("city", "").lower() == city.lower()]
            return filtered[:10]
        return self.scores[:10]
