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

        # 預先在背景 fetch 建築物，瀏覽器請求 /roads 時可直接從快取回傳
        def _prefetch(s, n, w, e):
            try:
                MapAPI.fetch_roads_bbox(s, n, w, e)
            except Exception:
                pass
        threading.Thread(
            target=_prefetch,
            args=(bounds["s"], bounds["n"], bounds["w"], bounds["e"]),
            daemon=True
        ).start()

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
        )

    except ValueError as e:
        return render_template("index.html", error=str(e), top10=scoreboard.get_top10())
    except Exception as e:
        return render_template("index.html",
                               error=f"發生錯誤: {str(e)}",
                               top10=scoreboard.get_top10())


@app.route("/roads")
def get_roads():
    # Preferred: explicit bounding box covering all treasure locations
    s = request.args.get("s", type=float)
    n = request.args.get("n", type=float)
    w = request.args.get("w", type=float)
    e = request.args.get("e", type=float)
    if None not in (s, n, w, e):
        try:
            return jsonify(MapAPI.fetch_roads_bbox(s, n, w, e))
        except Exception:
            return jsonify({"roads": {"type": "FeatureCollection", "features": []}, "buildings": []})
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
    try:
        from waitress import serve
        print("Starting with waitress (production WSGI)...")
        serve(app, host="0.0.0.0", port=5000, threads=8)
    except ImportError:
        print("waitress not found, falling back to Flask dev server (threaded)...")
        app.run(host="0.0.0.0", debug=False, port=5000, threaded=True)
