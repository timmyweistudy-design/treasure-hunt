import os
import json
import math
import time
import uuid
import random
import threading
from flask import Flask, render_template, request, session, jsonify, redirect, url_for, make_response
from game.models import Player, Scoreboard, Treasure
from game.map_api import MapAPI
from game.pathfinder import solve_tsp_exact, calculate_total_distance, haversine
from config import GAME_CONFIG

app = Flask(__name__)
app.secret_key = "treasure-hunt-fixed-key-2026"
scoreboard = Scoreboard()

# Pre-populated coords for common cities — skip Nominatim entirely for these
_KNOWN_CITIES: dict = {
    "taipei":       (25.0375198,  121.5636796),
    "台北":          (25.0375198,  121.5636796),
    "taichung":     (24.1477358,  120.6736482),
    "台中":          (24.1477358,  120.6736482),
    "tainan":       (22.9997281,  120.2270277),
    "台南":          (22.9997281,  120.2270277),
    "kaohsiung":    (22.6203348,  120.3120375),
    "高雄":          (22.6203348,  120.3120375),
    "tokyo":        (35.6761919,  139.6503106),
    "東京":          (35.6761919,  139.6503106),
    "osaka":        (34.6937249,  135.5022535),
    "大阪":          (34.6937249,  135.5022535),
    "kyoto":        (35.0212466,  135.7555968),
    "京都":          (35.0212466,  135.7555968),
    "seoul":        (37.5666791,  126.9782914),
    "首爾":          (37.5666791,  126.9782914),
    "hong kong":    (22.3193039,  114.1693611),
    "香港":          (22.3193039,  114.1693611),
    "singapore":    (1.357107,    103.8194992),
    "新加坡":         (1.357107,    103.8194992),
    "bangkok":      (13.7544238,  100.4930399),
    "曼谷":          (13.7544238,  100.4930399),
    "paris":        (48.8588897,  2.3200410),
    "london":       (51.5074456, -0.1277653),
    "new york":     (40.7127281, -74.0060152),
    "los angeles":  (34.0536909, -118.2427666),
    "sydney":       (-33.8688197, 151.2092955),
    "melbourne":    (-37.8142176, 144.9631608),
}

# ── 背景準備任務：req_id → {status, ...} ──────────────────────
_pending: dict = {}
# 準備好的遊戲資料（等 /game 路由來取）：game_key → render_args
_game_data: dict = {}
# city 快取：city_key → {lat, lon, treasures_list}
_city_cache: dict = {}
# 建築物預取協調
_pf_lock = threading.Lock()
_pf_events: dict = {}


def _prefetch_buildings(focus_points: list):
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


def _bg_prepare(req_id: str, player_name: str, city: str):
    """背景執行所有慢速 API 查詢，結果存入 _pending/_game_data。"""
    try:
        city_key = city.lower().strip()
        if city_key in _city_cache:
            cached = _city_cache[city_key]
            lat, lon = cached["lat"], cached["lon"]
            all_t = [Treasure(**d) for d in cached["treasures"]]
            count = min(GAME_CONFIG["treasure_count"], len(all_t))
            # spread selection from cache
            from game.map_api import _spread_select as _ss
            pool = [t.to_dict() for t in all_t]
            spread = _ss(pool, count)
            treasures = [Treasure(**d) for d in spread]
        else:
            if city_key in _KNOWN_CITIES:
                lat, lon = _KNOWN_CITIES[city_key]
            else:
                location = MapAPI.geocode(city)
                lat, lon = location["lat"], location["lon"]
            treasures = MapAPI.fetch_poi(lat, lon)
            if not treasures:
                _pending[req_id] = {"status": "error", "message": "此城市找不到足夠的地點，請嘗試其他城市"}
                return
            _city_cache[city_key] = {
                "lat": lat, "lon": lon,
                "treasures": [t.to_dict() for t in treasures],
            }

        for t in treasures:
            dist = haversine((lat, lon), (t.lat, t.lon))
            t.points = max(50, min(500, round((50 + dist * 0.3) / 10) * 10))

        player_coords = (lat, lon)
        optimal_route = solve_tsp_exact(player_coords, treasures)
        total_dist = calculate_total_distance(player_coords, optimal_route)

        # 動態正方形邊界：以起點為中心、恰好框住最遠寶藏（+20% margin）
        cos_lat = math.cos(math.radians(lat))
        dists_m = []
        for t in treasures:
            dlat_m = abs(t.lat - lat) * 111320
            dlon_m = abs(t.lon - lon) * (111320 * cos_lat)
            dists_m.append(max(dlat_m, dlon_m))
        half_m = max(dists_m) * 1.20 if dists_m else 800.0
        half_m = max(400.0, min(3000.0, half_m))   # 最小 400m、最大 3km
        half_lat = half_m / 111320.0
        half_lon = half_m / (111320.0 * cos_lat)
        bounds = {
            "s": lat - half_lat, "n": lat + half_lat,
            "w": lon - half_lon, "e": lon + half_lon,
        }
        focus_points = [(lat, lon)] + [(t.lat, t.lon) for t in treasures]
        _prefetch_buildings(focus_points)

        game_key = str(uuid.uuid4())
        _game_data[game_key] = {
            "player_name": player_name,
            "player_lat": lat, "player_lon": lon,
            "city": city,
            "optimal_route": optimal_route,
            "total_dist": round(total_dist),
            "time_limit": GAME_CONFIG["time_limit"],
            "collect_radius": GAME_CONFIG["collect_radius"],
            "treasures_json": json.dumps([t.to_dict() for t in treasures]),
            "optimal_order_json": json.dumps([t.id for t in optimal_route]),
            "route_coords_json": "[]",
            "bounds_json": json.dumps(bounds),
            "focus_points_json": json.dumps(focus_points),
            # session data
            "session_player": {
                "name": player_name, "lat": lat, "lon": lon,
                "score": 0, "found_treasures": [],
                "start_time": time.time(), "city": city,
            },
            "session_treasures": [t.to_dict() for t in treasures],
            "session_optimal_order": [t.id for t in optimal_route],
        }
        _pending[req_id] = {"status": "ready", "game_key": game_key}

    except Exception as e:
        _pending[req_id] = {"status": "error", "message": str(e)}


@app.route("/")
def index():
    return render_template("index.html", top10=scoreboard.get_top10())


@app.route("/start", methods=["POST"])
def start_game():
    player_name = request.form.get("player_name", "玩家").strip()
    city = request.form.get("city", "Taipei").strip()
    req_id = str(uuid.uuid4())
    _pending[req_id] = {"status": "loading"}
    threading.Thread(target=_bg_prepare, args=(req_id, player_name, city), daemon=True).start()

    # 立刻回傳 loading 頁，完全不等 API（解決 Render 30s timeout）
    return f'''<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<title>準備中 - {city}</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0d1117;display:flex;align-items:center;justify-content:center;
     height:100vh;font-family:"Noto Sans TC",sans-serif;color:#fff}}
.card{{text-align:center;padding:40px 50px;background:#1a2540;border-radius:18px;
       box-shadow:0 16px 48px rgba(0,0,0,.65);max-width:340px;width:90%}}
.spin{{width:52px;height:52px;border:4px solid rgba(255,255,255,.1);
       border-top-color:#7ec8f8;border-radius:50%;
       animation:spin .8s linear infinite;margin:0 auto 20px}}
@keyframes spin{{to{{transform:rotate(360deg)}}}}
.title{{font-size:17px;font-weight:bold;margin-bottom:18px;
        background:linear-gradient(90deg,#7ec8f8,#34a853);
        -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}}
.step{{font-size:14px;color:#90caf9;min-height:22px;margin-bottom:6px}}
.sub{{font-size:12px;color:#546e7a;min-height:18px;margin-bottom:20px}}
.err{{color:#ef5350;font-size:13px;display:none;margin-bottom:14px}}
.btn{{padding:9px 24px;border:none;border-radius:20px;cursor:pointer;
      font-size:13px;font-weight:bold;background:#e53935;color:#fff;display:none}}
</style>
</head>
<body>
<div class="card">
  <div class="title">🏙️ 準備 {city}</div>
  <div class="spin" id="sp"></div>
  <div class="step" id="st">🔍 搜尋附近景點…</div>
  <div class="sub"  id="sb">連線地圖資料庫中</div>
  <div class="err"  id="er"></div>
  <button class="btn" id="bt" onclick="location.href='/'">← 回首頁</button>
</div>
<script>
const ID='{req_id}';
const STEPS=['🔍 搜尋附近景點…','📍 計算最佳路線…','🗺️ 整理地圖資料…','⚙️ 即將完成…'];
let t=0;
async function poll(){{
  t++;
  document.getElementById('st').textContent=STEPS[Math.min(t-1,STEPS.length-1)];
  document.getElementById('sb').textContent='已等待 '+(t*2)+' 秒';
  if(t>30){{showErr('等待逾時，請重試');return;}}
  try{{
    const r=await fetch('/start/poll?id='+ID);
    const d=await r.json();
    if(d.status==='ready'){{window.location.href='/game';return;}}
    if(d.status==='error'){{showErr(d.message||'發生錯誤');return;}}
  }}catch(e){{document.getElementById('sb').textContent='重新連線中…';}}
  setTimeout(poll,2000);
}}
function showErr(msg){{
  document.getElementById('sp').style.display='none';
  document.getElementById('er').textContent=msg;
  document.getElementById('er').style.display='block';
  document.getElementById('bt').style.display='inline-block';
}}
setTimeout(poll,2000);
</script>
</body>
</html>'''


@app.route("/start/poll")
def start_poll():
    req_id = request.args.get("id", "")
    entry = _pending.get(req_id)
    if not entry:
        return jsonify({"status": "error", "message": "逾時，請重新開始"})
    if entry["status"] == "loading":
        return jsonify({"status": "loading"})
    if entry["status"] == "error":
        _pending.pop(req_id, None)
        return jsonify({"status": "error", "message": entry.get("message", "發生錯誤")})

    # 準備好：把 session 寫入，存 game_key 讓 /game 路由取資料
    game_key = entry["game_key"]
    gd = _game_data.get(game_key, {})
    session["player"] = gd.get("session_player", {})
    session["treasures"] = gd.get("session_treasures", [])
    session["optimal_order"] = gd.get("session_optimal_order", [])
    session["game_key"] = game_key
    _pending.pop(req_id, None)
    return jsonify({"status": "ready"})


@app.route("/game")
def game():
    game_key = session.get("game_key")
    if not game_key or game_key not in _game_data:
        return redirect("/")
    gd = _game_data.pop(game_key)
    session.pop("game_key", None)
    resp = make_response(render_template("game.html",
        player_name=gd["player_name"],
        player_lat=gd["player_lat"],
        player_lon=gd["player_lon"],
        city=gd["city"],
        optimal_route=gd["optimal_route"],
        total_dist=gd["total_dist"],
        time_limit=gd["time_limit"],
        collect_radius=gd["collect_radius"],
        treasures_json=gd["treasures_json"],
        optimal_order_json=gd["optimal_order_json"],
        route_coords_json=gd["route_coords_json"],
        bounds_json=gd["bounds_json"],
        focus_points_json=gd["focus_points_json"],
    ))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp


@app.route("/roads")
def get_roads():
    _empty = {"roads": {"type": "FeatureCollection", "features": []}, "buildings": []}
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
    s = request.args.get("s", type=float)
    n = request.args.get("n", type=float)
    w = request.args.get("w", type=float)
    e = request.args.get("e", type=float)
    if None not in (s, n, w, e):
        try:
            return jsonify(MapAPI.fetch_roads_bbox(s, n, w, e))
        except Exception:
            return jsonify(_empty)
    lat = request.args.get("lat", type=float)
    lon = request.args.get("lon", type=float)
    if lat is None or lon is None:
        return jsonify(_empty), 400
    try:
        return jsonify(MapAPI.fetch_roads(lat, lon))
    except Exception:
        return jsonify(_empty)


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


@app.route("/score_add", methods=["POST"])
def score_add():
    player_data = session.get("player", {})
    if not player_data:
        return jsonify({"status": "error"}), 400
    bonus = int((request.get_json(silent=True) or {}).get("bonus", 0))
    player_data["score"] = player_data.get("score", 0) + bonus
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
    elapsed = min(player.elapsed_time, GAME_CONFIG["time_limit"])
    time_bonus = max(0, int((GAME_CONFIG["time_limit"] - elapsed) * GAME_CONFIG["time_bonus_rate"]))
    player.score += time_bonus
    scoreboard.save_score(player, city)
    found = [t for t in treasures_data if t["found"]]
    return render_template("finish.html",
                           player=player, city=city,
                           found_count=len(found), total=len(treasures_data),
                           time_bonus=time_bonus, top10=scoreboard.get_top10(city))


@app.route("/health")
def health():
    return "ok", 200


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
