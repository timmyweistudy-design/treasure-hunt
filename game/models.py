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
        # 同名只保留最佳紀錄（分高者優先；同分取用時短者）
        name_key = player.name.strip().lower()
        existing = next(
            (i for i, s in enumerate(self.scores)
             if s.get("name", "").strip().lower() == name_key),
            None
        )
        if existing is not None:
            old = self.scores[existing]
            if (entry["score"], -entry["time"]) > (old["score"], -old["time"]):
                self.scores[existing] = entry   # 新紀錄更好，取代
            # 否則保留舊紀錄，不寫入
        else:
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
        pool = self.scores
        if city:
            pool = [s for s in pool if s.get("city", "").lower() == city.lower()]
        # 同名只保留最高分那筆（scores 已按 -score 排序，故第一次出現即最高）
        seen = set()
        unique = []
        for s in pool:
            key = s.get("name", "").strip().lower()
            if key not in seen:
                seen.add(key)
                unique.append(s)
            if len(unique) >= 10:
                break
        return unique

    def get_by_city(self, top_n: int = 5):
        """回傳 {city: [top_n entries]}，城市依榜首分數降序排列。"""
        city_map = {}
        for s in self.scores:            # scores 已按 -score 排序
            city = (s.get("city") or "?").strip()
            if city not in city_map:
                city_map[city] = []
            if len(city_map[city]) < top_n:
                city_map[city].append(s)
        # 城市順序：榜首分數最高的城市排前面
        sorted_cities = sorted(
            city_map.items(),
            key=lambda kv: kv[1][0]["score"] if kv[1] else 0,
            reverse=True
        )
        return sorted_cities   # list of (city, entries)


# ── 成就系統 ───────────────────────────────────────────────────────────
_GH_ACH_FILE = "achievements.json"
_GH_ACH_API  = f"https://api.github.com/repos/{_GH_REPO}/contents/{_GH_ACH_FILE}"


def _gh_ach_load():
    """從 GitHub 讀取成就資料，失敗或不存在回傳 ({}, None)。"""
    if not _GH_TOKEN:
        return None
    try:
        import requests
        r = requests.get(_GH_ACH_API, headers=_GH_HEADS, timeout=5)
        if r.status_code == 404:
            return {}, None
        if r.status_code != 200:
            return None
        data = r.json()
        return json.loads(base64.b64decode(data["content"]).decode()), data["sha"]
    except Exception:
        return None


def _gh_ach_save(achs: dict, sha):
    """把成就資料寫回 GitHub，失敗靜默。"""
    if not _GH_TOKEN:
        return
    try:
        import requests
        content = base64.b64encode(
            json.dumps(achs, ensure_ascii=False, indent=2).encode()
        ).decode()
        payload = {
            "message": "update achievements",
            "content": content,
        }
        if sha:
            payload["sha"] = sha
        requests.put(_GH_ACH_API, headers=_GH_HEADS, timeout=8, json=payload)
    except Exception:
        pass


class AchievementStore:
    def __init__(self, filepath="data/achievements.json"):
        self.filepath = filepath
        self._sha = None
        self._data = self._load()   # {player_name: {ach_id: bool}}

    def _load(self):
        result = _gh_ach_load()
        if result is not None:
            data, self._sha = result
            return data if isinstance(data, dict) else {}
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def get_player(self, name: str) -> dict:
        """取得玩家的成就字典（副本），若無記錄回傳 {}。"""
        return dict(self._data.get(name, {}))

    def save_player(self, name: str, achievements: dict):
        """儲存/更新玩家成就。"""
        self._data[name] = achievements
        _gh_ach_save(self._data, self._sha)
        # 刷新 SHA 供下次寫入
        result = _gh_ach_load()
        if result is not None:
            _, self._sha = result
        # 本機備份
        dirp = os.path.dirname(self.filepath)
        if dirp:
            os.makedirs(dirp, exist_ok=True)
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get_all_players(self) -> dict:
        return dict(self._data)
