import os
import json
import time
import threading
from flask import Flask, render_template, request, session, jsonify, redirect, url_for
from game.models import Player, Scoreboard
from game.map_api import MapAPI
from game.pathfinder import solve_tsp_exact, calculate_total_distance, haversine
from config import GAME_CONFIG

app = Flask(__name__)
app.secret_key = "treasure-hunt-fixed-key-2026"
scoreboard = Scoreboard()

# 建築物預先快取協調：防止 /start 背景 fetch 和 /roads 同時打 Overpass
_pf_lock = threading.Lock()
_pf_events: dict = {}   # bbox_key → threading.Event（fetch 進行中時存在）

def _prefetch_buildings(focus_points: list):
    """背景預取建築物（用 focus point 小 bbox 聯合查詢）。"""
    pts = focus_points[:14]
    key = "fp_" + "_".join(f"{round(p[0],3)},{round(p[1],3)}" for p in pts)
    with _pf_lock:
        if key in MapAPI._road_cache or key in _pf_events:
            return
        evt = threading.Event()
        _pf_events[key] = evt
    def _run():
        try:
            MapAPI.fetch_roads_focused(pts)
        except Exception:
            pass
        finally:
            evt.set()
            with _pf_lock:
                _pf_events.pop(key, None)
    threading.Thread(target=_run, daemon=True).start()


@app.route("/")
def index():
    return render_template("index.html", top10=scoreboard.get_top10())


@app.route("/start", methods=["POST"])
def start_game():
    player_name = request.form.get("player_name", "玩家").strip()
    city = request.form.get("city", "Taipei").strip()

    try:
        location = MapAPI.geocode(city)
        lat, lon = location["lat"], location["lon"]

        treasures = MapAPI.fetch_poi(lat, lon)
        if not treasures:
            return render_template("index.html",
                                   error="此城市找不到足夠的地點，請嘗試其他城市",
                                   top10=scoreboard.get_top10())

        # 依距離設定寶藏分數：越遠分越高（50~500分，四捨五入到10）
        for t in treasures:
            dist = haversine((lat, lon), (t.lat, t.lon))
            t.points = max(50, min(500, round((50 + dist * 0.3) / 10) * 10))

        player_coords = (lat, lon)
        optimal_route = solve_tsp_exact(player_coords, treasures)
        total_dist = calculate_total_distance(player_coords, optimal_route)

        all_coords = [player_coords] + [t.coords for t in optimal_route]
        route_coords = MapAPI.get_route(all_coords)

        # Bounding box covering start + all treasure locations (for building collision)
        all_lats = [lat] + [t.lat for t in treasures]
        all_lons = [lon] + [t.lon for t in treasures]
        margin = 0.002  # ~220m padding around edges
        bounds = {
            "s": min(all_lats) - margin,
            "n": max(all_lats) + margin,
            "w": min(all_lons) - margin,
            "e": max(all_lons) + margin,
        }

        # 焦點點：出發點＋各寶藏＋路線取樣（最多 14 點）
        focus_points = [(lat, lon)] + [(t.lat, t.lon) for t in treasures]
        if route_coords:
            step = max(1, len(route_coords) // 8)
            for coord in route_coords[::step]:
                focus_points.append((coord[1], coord[0]))  # [lon,lat]→[lat,lon]
        focus_points = focus_points[:14]

        # 背景預取建築物（用 focus point 小 bbox 聯合查詢）
        _prefetch_buildings(focus_points)

        session["player"] = {
            "name": player_name,
            "lat": lat, "lon": lon,
            "score": 0,
            "found_treasures": [],
            "start_time": time.time(),
            "city": city
        }
        session["treasures"] = [t.to_dict() for t in treasures]
        session["optimal_order"] = [t.id for t in optimal_route]

        return render_template("game.html",
            player_name=player_name,
            player_lat=lat,
            player_lon=lon,
            city=city,
            optimal_route=optimal_route,
            total_dist=round(total_dist),
            time_limit=GAME_CONFIG["time_limit"],
            collect_radius=GAME_CONFIG["collect_radius"],
            treasures_json=json.dumps([t.to_dict() for t in treasures]),
            optimal_order_json=json.dumps([t.id for t in optimal_route]),
            route_coords_json=json.dumps(route_coords),
            bounds_json=json.dumps(bounds),
            focus_points_json=json.dumps(focus_points),
        )

    except ValueError as e:
        return render_template("index.html", error=str(e), top10=scoreboard.get_top10())
    except Exception as e:
        return render_template("index.html",
                               error=f"發生錯誤: {str(e)}",
                               top10=scoreboard.get_top10())


@app.route("/roads")
def get_roads():
    _empty = {"roads": {"type": "FeatureCollection", "features": []}, "buildings": []}

    # 優先：focus points 聯合小 bbox 查詢
    pts_raw = request.args.get("pts")
    if pts_raw:
        try:
            pts = json.loads(pts_raw)[:14]
            key = "fp_" + "_".join(f"{round(p[0],3)},{round(p[1],3)}" for p in pts)
            with _pf_lock:
                evt = _pf_events.get(key)
            if evt:
                evt.wait(timeout=24)
            return jsonify(MapAPI.fetch_roads_focused(pts))
        except Exception:
            return jsonify(_empty)

    # 備援：舊版全 bbox 查詢
    s = request.args.get("s", type=float)
    n = request.args.get("n", type=float)
    w = request.args.get("w", type=float)
    e = request.args.get("e", type=float)
    if None not in (s, n, w, e):
        key = (round(s, 3), round(n, 3), round(w, 3), round(e, 3))
        with _pf_lock:
            evt = _pf_events.get(key)
        if evt:
            evt.wait(timeout=24)
        try:
            return jsonify(MapAPI.fetch_roads_bbox(s, n, w, e))
        except Exception:
            return jsonify(_empty)
    # Fallback: single point + fixed radius
    lat = request.args.get("lat", type=float)
    lon = request.args.get("lon", type=float)
    if lat is None or lon is None:
        return jsonify({"roads": {"type": "FeatureCollection", "features": []}, "buildings": []}), 400
    try:
        return jsonify(MapAPI.fetch_roads(lat, lon))
    except Exception:
        return jsonify({"roads": {"type": "FeatureCollection", "features": []}, "buildings": []})


@app.route("/collect/<treasure_id>", methods=["POST"])
def collect_treasure(treasure_id):
    treasures_data = session.get("treasures", [])
    player_data = session.get("player", {})

    if not player_data:
        return jsonify({"status": "error", "msg": "session 過期"}), 400

    order_bonus = 0
    if request.is_json:
        order_bonus = int(request.get_json(silent=True).get("order_bonus", 0))

    for t in treasures_data:
        if t["id"] == treasure_id and not t["found"]:
            t["found"] = True
            player_data["score"] = player_data.get("score", 0) + t["points"] + order_bonus
            player_data.setdefault("found_treasures", []).append(treasure_id)
            break

    session["treasures"] = treasures_data
    session["player"] = player_data

    found_count = sum(1 for t in treasures_data if t["found"])
    total = len(treasures_data)

    status = "win" if found_count == total else "ok"
    return jsonify({"status": status, "score": player_data["score"],
                    "found": found_count, "total": total})


@app.route("/penalty", methods=["POST"])
def apply_penalty():
    player_data = session.get("player", {})
    if not player_data:
        return jsonify({"status": "error"}), 400
    amount = int((request.get_json(silent=True) or {}).get("amount", 0))
    player_data["score"] = max(0, player_data.get("score", 0) - amount)
    session["player"] = player_data
    return jsonify({"status": "ok", "score": player_data["score"]})


@app.route("/finish")
def finish_game():
    player_data = session.get("player", {})
    treasures_data = session.get("treasures", [])

    if not player_data:
        return redirect(url_for("index"))

    city = player_data.get("city", "")

    player = Player(
        name=player_data.get("name", "玩家"),
        lat=player_data.get("lat", 0),
        lon=player_data.get("lon", 0),
        score=player_data.get("score", 0),
        found_treasures=player_data.get("found_treasures", []),
        start_time=player_data.get("start_time", time.time())
    )

    # 時間獎勵：每剩 1 秒 +2 分（最多 600 分）
    elapsed = min(player.elapsed_time, GAME_CONFIG["time_limit"])
    time_bonus = max(0, int((GAME_CONFIG["time_limit"] - elapsed) * GAME_CONFIG["time_bonus_rate"]))
    player.score += time_bonus

    scoreboard.save_score(player, city)

    found = [t for t in treasures_data if t["found"]]
    return render_template("finish.html",
                           player=player,
                           city=city,
                           found_count=len(found),
                           total=len(treasures_data),
                           time_bonus=time_bonus,
                           top10=scoreboard.get_top10(city))


@app.errorhandler(404)
def not_found(e):
    return render_template("index.html", error="頁面不存在"), 404


@app.errorhandler(500)
def server_error(e):
    return render_template("index.html", error="伺服器發生錯誤"), 500


if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    port = int(os.environ.get("PORT", 5000))
    try:
        from waitress import serve
        print(f"Starting with waitress on port {port}...")
        serve(app, host="0.0.0.0", port=port, threads=8)
    except ImportError:
        print(f"waitress not found, falling back to Flask dev server on port {port}...")
        app.run(host="0.0.0.0", debug=False, port=port, threaded=True)
