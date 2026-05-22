import os
import json
import math
import time
import uuid
import random
import logging
import threading
from flask import Flask, render_template, request, session, jsonify, redirect, url_for, make_response
from game.models import Player, Scoreboard, Treasure
from game.map_api import MapAPI
from game.pathfinder import solve_tsp_exact, calculate_total_distance, haversine
from config import GAME_CONFIG

app = Flask(__name__)
app.secret_key = "treasure-hunt-fixed-key-2026"
scoreboard = Scoreboard()


TREASURE_TIERS = [
    {"target_m": 200},  {"target_m": 200},
    {"target_m": 450},  {"target_m": 450},
    {"target_m": 700},  {"target_m": 700},
    {"target_m": 850},  {"target_m": 850},
    {"target_m": 1000}, {"target_m": 1000},
]

_MIN_TREASURE_SPREAD = 150  # metres — minimum distance between any two placed treasures

def _assign_tiers(raw_pois, origin_lat, origin_lon):
    """
    每層兩個寶藏盡量放在圈的對邊（最大化彼此距離），
    所有寶藏間距 >= _MIN_TREASURE_SPREAD。
    容差從 ±80m 遞增，每次先找距離夠遠的候選，沒有才放寬間距限制。
    """
    scored = [(haversine((origin_lat, origin_lon), (p["lat"], p["lon"])), i, p)
              for i, p in enumerate(raw_pois)]
    used = set()
    result = []

    def _far_enough(p):
        return all(haversine((p["lat"], p["lon"]), (t.lat, t.lon)) >= _MIN_TREASURE_SPREAD
                   for t in result)

    for tier_idx, tier in enumerate(TREASURE_TIERS):
        target = tier["target_m"]
        chosen_i, chosen_p = None, None

        min_d = target * 0.5  # never pick a POI closer than half the target distance
        tolerances = list(range(50, 500, 50)) + [float('inf')]
        for tolerance in tolerances:
            raw_pool = [(i, p) for d, i, p in scored
                        if i not in used and d >= min_d and abs(d - target) <= tolerance]
            if not raw_pool:
                continue
            # Prefer candidates that keep min spread; fall back if none qualify
            pool = [(i, p) for i, p in raw_pool if _far_enough(p)] or raw_pool

            # Odd index = 2nd of ring pair → pick most opposite side of the ring.
            # Strategy: maximise the angle from origin between the two picks,
            # i.e. minimise their dot-product of direction-vectors from origin.
            # This puts them on opposite edges of the imaginary square.
            if tier_idx % 2 == 1 and result:
                prev = result[-1]
                dprev_lat = prev.lat - origin_lat
                dprev_lon = prev.lon - origin_lon
                chosen_i, chosen_p = max(
                    pool,
                    key=lambda x: -(dprev_lat * (x[1]["lat"] - origin_lat) +
                                    dprev_lon * (x[1]["lon"] - origin_lon))
                )
            else:
                chosen_i, chosen_p = random.choice(pool)
            break

        if chosen_p:
            used.add(chosen_i)
            dist_m = int(round(haversine((origin_lat, origin_lon),
                                         (chosen_p["lat"], chosen_p["lon"]))))
            result.append(Treasure(
                id=f"t{tier_idx}", name=chosen_p["name"],
                lat=chosen_p["lat"], lon=chosen_p["lon"],
                category=chosen_p["category"],
                points=dist_m,  # 分數 = 距出生點公尺數
            ))
        else:
            logging.warning("_assign_tiers: tier %d (target %dm) skipped — no suitable POI found",
                            tier_idx, tier["target_m"])
    return result

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
    "hsinchu":      (24.8066333,  120.9686833),
    "新竹":          (24.8066333,  120.9686833),
    "keelung":      (25.1283074,  121.7404153),
    "基隆":          (25.1283074,  121.7404153),
    "taoyuan":      (24.9936281,  121.3009798),
    "桃園":          (24.9936281,  121.3009798),
    "miaoli":       (24.5636947,  120.8214221),
    "苗栗":          (24.5636947,  120.8214221),
    "changhua":     (24.0651839,  120.5169431),
    "彰化":          (24.0651839,  120.5169431),
    "nantou":       (23.9609636,  120.9718751),
    "南投":          (23.9609636,  120.9718751),
    "yunlin":       (23.7092126,  120.4313386),
    "雲林":          (23.7092126,  120.4313386),
    "chiayi":       (23.4800667,  120.4491212),
    "嘉義":          (23.4800667,  120.4491212),
    "pingtung":     (22.6682017,  120.4886622),
    "屏東":          (22.6682017,  120.4886622),
    "yilan":        (24.7021073,  121.7377949),
    "宜蘭":          (24.7021073,  121.7377949),
    "hualien":      (23.9871589,  121.6015959),
    "花蓮":          (23.9871589,  121.6015959),
    "taitung":      (22.7972211,  121.0706986),
    "台東":          (22.7972211,  121.0706986),
    "penghu":       (23.5682842,  119.5793916),
    "澎湖":          (23.5682842,  119.5793916),
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
    # ── 日本 ──────────────────────────────────────────────────────
    "nagoya":       (35.1814464,  136.9063576),
    "名古屋":         (35.1814464,  136.9063576),
    "sapporo":      (43.0618713,  141.3544468),
    "札幌":          (43.0618713,  141.3544468),
    "fukuoka":      (33.5901838,  130.4016888),
    "福岡":          (33.5901838,  130.4016888),
    "hiroshima":    (34.3853419,  132.4552976),
    "廣島":          (34.3853419,  132.4552976),
    "yokohama":     (35.4437078,  139.6380256),
    "橫濱":          (35.4437078,  139.6380256),
    # ── 中國 ──────────────────────────────────────────────────────
    "beijing":      (39.9041999,  116.4073963),
    "北京":          (39.9041999,  116.4073963),
    "shanghai":     (31.2303904,  121.4737021),
    "上海":          (31.2303904,  121.4737021),
    "guangzhou":    (23.1290964,  113.2643514),
    "廣州":          (23.1290964,  113.2643514),
    "shenzhen":     (22.5430556,  114.0579185),
    "深圳":          (22.5430556,  114.0579185),
    "chengdu":      (30.5722926,  104.0665677),
    "成都":          (30.5722926,  104.0665677),
    "chongqing":    (29.5627762,  106.5518663),
    "重慶":          (29.5627762,  106.5518663),
    "wuhan":        (30.5927632,  114.3054824),
    "武漢":          (30.5927632,  114.3054824),
    "nanjing":      (32.0603203,  118.7968793),
    "南京":          (32.0603203,  118.7968793),
    "hangzhou":     (30.2741105,  120.1550650),
    "杭州":          (30.2741105,  120.1550650),
    "xian":         (34.3416242,  108.9398427),
    "xi'an":        (34.3416242,  108.9398427),
    "西安":          (34.3416242,  108.9398427),
    "tianjin":      (39.1235895,  117.1980785),
    "天津":          (39.1235895,  117.1980785),
    "macau":        (22.1987368,  113.5438894),
    "澳門":          (22.1987368,  113.5438894),
    # ── 韓國 ──────────────────────────────────────────────────────
    "busan":        (35.1795543,  129.0756416),
    "釜山":          (35.1795543,  129.0756416),
    "incheon":      (37.4562557,  126.7052062),
    "仁川":          (37.4562557,  126.7052062),
    # ── 東南亞 ─────────────────────────────────────────────────────
    "jakarta":      (-6.2087634,  106.8455882),
    "雅加達":         (-6.2087634,  106.8455882),
    "kuala lumpur": (3.1385165,   101.6867994),
    "吉隆坡":         (3.1385165,   101.6867994),
    "ho chi minh":  (10.8230989,  106.6296638),
    "胡志明市":        (10.8230989,  106.6296638),
    "hanoi":        (21.0277644,  105.8341598),
    "河內":          (21.0277644,  105.8341598),
    "manila":       (14.5995124,  120.9842195),
    "馬尼拉":         (14.5995124,  120.9842195),
    "yangon":       (16.8660694,   96.1951005),
    "仰光":          (16.8660694,   96.1951005),
    "phnom penh":   (11.5563738,  104.9282099),
    "金邊":          (11.5563738,  104.9282099),
    "vientiane":    (17.9757058,  102.6331035),
    "永珍":          (17.9757058,  102.6331035),
    "colombo":      (6.9270786,    79.8611940),
    "可倫坡":         (6.9270786,    79.8611940),
    "kathmandu":    (27.7172453,   85.3239605),
    "加德滿都":        (27.7172453,   85.3239605),
    "dhaka":        (23.8104753,   90.4119873),
    "達卡":          (23.8104753,   90.4119873),
    # ── 南亞 ──────────────────────────────────────────────────────
    "mumbai":       (19.0759837,   72.8776559),
    "孟買":          (19.0759837,   72.8776559),
    "delhi":        (28.6517178,   77.2219388),
    "new delhi":    (28.6141531,   77.2024912),
    "新德里":         (28.6141531,   77.2024912),
    "德里":          (28.6517178,   77.2219388),
    "kolkata":      (22.5744174,   88.3629016),
    "加爾各答":        (22.5744174,   88.3629016),
    "bangalore":    (12.9715987,   77.5945627),
    "班加羅爾":        (12.9715987,   77.5945627),
    "karachi":      (24.8607343,   67.0011364),
    "喀拉蚩":         (24.8607343,   67.0011364),
    "islamabad":    (33.7294516,   73.0931028),
    "伊斯蘭馬巴德":      (33.7294516,   73.0931028),
    "lahore":       (31.5203696,   74.3587473),
    "拉合爾":         (31.5203696,   74.3587473),
    # ── 中亞 / 西亞 ────────────────────────────────────────────────
    "tehran":       (35.6891975,   51.3889736),
    "德黑蘭":         (35.6891975,   51.3889736),
    "baghdad":      (33.3152273,   44.3660671),
    "巴格達":         (33.3152273,   44.3660671),
    "riyadh":       (24.7135517,   46.6752957),
    "利雅德":         (24.7135517,   46.6752957),
    "dubai":        (25.2048493,   55.2707828),
    "杜拜":          (25.2048493,   55.2707828),
    "abu dhabi":    (24.4538352,   54.3773438),
    "阿布達比":        (24.4538352,   54.3773438),
    "doha":         (25.2854473,   51.5310398),
    "多哈":          (25.2854473,   51.5310398),
    "kuwait city":  (29.3796532,   47.9734051),
    "科威特城":        (29.3796532,   47.9734051),
    "muscat":       (23.5880307,   58.3828717),
    "馬斯喀特":        (23.5880307,   58.3828717),
    "amman":        (31.9453683,   35.9284082),
    "安曼":          (31.9453683,   35.9284082),
    "beirut":       (33.8937913,   35.5017767),
    "貝魯特":         (33.8937913,   35.5017767),
    "damascus":     (33.5102035,   36.2913386),
    "大馬士革":        (33.5102035,   36.2913386),
    "tel aviv":     (32.0852999,   34.7818064),
    "特拉維夫":        (32.0852999,   34.7818064),
    "jerusalem":    (31.7683040,   35.2137150),
    "耶路撒冷":        (31.7683040,   35.2137150),
    "ankara":       (39.9333635,   32.8597419),
    "安卡拉":         (39.9333635,   32.8597419),
    "istanbul":     (41.0082376,   28.9783589),
    "伊斯坦堡":        (41.0082376,   28.9783589),
    "ulaanbaatar":  (47.8864438,  106.9057439),
    "烏蘭巴托":        (47.8864438,  106.9057439),
    "tashkent":     (41.2994958,   69.2400734),
    "塔什干":         (41.2994958,   69.2400734),
    "almaty":       (43.2220146,   76.8512485),
    "阿拉木圖":        (43.2220146,   76.8512485),
    "kabul":        (34.5553494,   69.2074758),
    "喀布爾":         (34.5553494,   69.2074758),
    "baku":         (40.4092617,   49.8670924),
    "巴庫":          (40.4092617,   49.8670924),
    "tbilisi":      (41.6938073,   44.8014990),
    "提比里斯":        (41.6938073,   44.8014990),
    "yerevan":      (40.1872023,   44.5151729),
    "葉里溫":         (40.1872023,   44.5151729),
    # ── 歐洲 ──────────────────────────────────────────────────────
    "paris":        (48.8588897,   2.3200410),
    "巴黎":          (48.8588897,   2.3200410),
    "london":       (51.5074456,  -0.1277653),
    "倫敦":          (51.5074456,  -0.1277653),
    "berlin":       (52.5200066,  13.4049540),
    "柏林":          (52.5200066,  13.4049540),
    "amsterdam":    (52.3727598,   4.8936041),
    "阿姆斯特丹":       (52.3727598,   4.8936041),
    "rome":         (41.9027835,  12.4963655),
    "羅馬":          (41.9027835,  12.4963655),
    "madrid":       (40.4167754,  -3.7037902),
    "馬德里":         (40.4167754,  -3.7037902),
    "barcelona":    (41.3850639,   2.1734035),
    "巴塞隆納":        (41.3850639,   2.1734035),
    "lisbon":       (38.7222524,  -9.1393366),
    "里斯本":         (38.7222524,  -9.1393366),
    "vienna":       (48.2081743,  16.3738189),
    "維也納":         (48.2081743,  16.3738189),
    "brussels":     (50.8503463,   4.3517211),
    "布魯塞爾":        (50.8503463,   4.3517211),
    "zurich":       (47.3768866,   8.5417025),
    "蘇黎世":         (47.3768866,   8.5417025),
    "geneva":       (46.2043907,   6.1431577),
    "日內瓦":         (46.2043907,   6.1431577),
    "bern":         (46.9479739,   7.4474468),
    "伯恩":          (46.9479739,   7.4474468),
    "stockholm":    (59.3293235,  18.0685808),
    "斯德哥爾摩":       (59.3293235,  18.0685808),
    "oslo":         (59.9138688,  10.7522454),
    "奧斯陸":         (59.9138688,  10.7522454),
    "copenhagen":   (55.6760968,  12.5683371),
    "哥本哈根":        (55.6760968,  12.5683371),
    "helsinki":     (60.1698557,  24.9383791),
    "赫爾辛基":        (60.1698557,  24.9383791),
    "warsaw":       (52.2296756,  21.0122287),
    "華沙":          (52.2296756,  21.0122287),
    "prague":       (50.0755381,  14.4378005),
    "布拉格":         (50.0755381,  14.4378005),
    "budapest":     (47.4979937,  19.0401578),
    "布達佩斯":        (47.4979937,  19.0401578),
    "athens":       (37.9838096,  23.7275388),
    "雅典":          (37.9838096,  23.7275388),
    "bucharest":    (44.4267674,  26.1025384),
    "布加勒斯特":       (44.4267674,  26.1025384),
    "sofia":        (42.6976953,  23.3218823),
    "索非亞":         (42.6976953,  23.3218823),
    "belgrade":     (44.8176506,  20.4568974),
    "貝爾格萊德":       (44.8176506,  20.4568974),
    "zagreb":       (45.8150108,  15.9819189),
    "薩格勒布":        (45.8150108,  15.9819189),
    "bratislava":   (48.1485965,  17.1077477),
    "布拉提斯拉瓦":      (48.1485965,  17.1077477),
    "riga":         (56.9460079,  24.1059488),
    "里加":          (56.9460079,  24.1059488),
    "tallinn":      (59.4369608,  24.7535746),
    "塔林":          (59.4369608,  24.7535746),
    "vilnius":      (54.6871555,  25.2796514),
    "維爾紐斯":        (54.6871555,  25.2796514),
    "kyiv":         (50.4501000,  30.5234000),
    "基輔":          (50.4501000,  30.5234000),
    "moscow":       (55.7558000,  37.6173000),
    "莫斯科":         (55.7558000,  37.6173000),
    "saint petersburg": (59.9310584, 30.3609096),
    "聖彼得堡":        (59.9310584,  30.3609096),
    "minsk":        (53.9006011,  27.5590010),
    "明斯克":         (53.9006011,  27.5590010),
    "reykjavik":    (64.1265206, -21.8174393),
    "雷克雅維克":       (64.1265206, -21.8174393),
    "dublin":       (53.3498006,  -6.2602964),
    "都柏林":         (53.3498006,  -6.2602964),
    "edinburgh":    (55.9533456,  -3.1883749),
    "愛丁堡":         (55.9533456,  -3.1883749),
    "munich":       (48.1351253,  11.5819806),
    "慕尼黑":         (48.1351253,  11.5819806),
    "hamburg":      (53.5500067,   9.9999651),
    "漢堡":          (53.5500067,   9.9999651),
    "frankfurt":    (50.1109221,   8.6821267),
    "法蘭克福":        (50.1109221,   8.6821267),
    "milan":        (45.4654219,   9.1859243),
    "米蘭":          (45.4654219,   9.1859243),
    "naples":       (40.8517746,  14.2681244),
    "那不勒斯":        (40.8517746,  14.2681244),
    "lyon":         (45.7578137,   4.8320114),
    "里昂":          (45.7578137,   4.8320114),
    "marseille":    (43.2961743,   5.3699525),
    "馬賽":          (43.2961743,   5.3699525),
    "porto":        (41.1494512,  -8.6107884),
    "波爾圖":         (41.1494512,  -8.6107884),
    "seville":      (37.3882364,  -5.9823296),
    "塞維亞":         (37.3882364,  -5.9823296),
    "valencia":     (39.4699075,  -0.3762881),
    "瓦倫西亞":        (39.4699075,  -0.3762881),
    "nicosia":      (35.1855659,   33.3822764),
    "尼科西亞":        (35.1855659,   33.3822764),
    "valletta":     (35.8989818,   14.5136759),
    "瓦萊塔":         (35.8989818,   14.5136759),
    "luxembourg":   (49.6116579,   6.1319346),
    "盧森堡":         (49.6116579,   6.1319346),
    "monaco":       (43.7384176,   7.4246158),
    "摩納哥":         (43.7384176,   7.4246158),
    "andorra":      (42.5063174,   1.5218355),
    "安道爾":         (42.5063174,   1.5218355),
    "chisinau":     (47.0245117,  28.8322923),
    "基希訥烏":        (47.0245117,  28.8322923),
    # ── 北美洲 ─────────────────────────────────────────────────────
    "new york":     (40.7127281, -74.0060152),
    "紐約":          (40.7127281, -74.0060152),
    "los angeles":  (34.0536909, -118.2427666),
    "洛杉磯":         (34.0536909, -118.2427666),
    "chicago":      (41.8781136, -87.6297982),
    "芝加哥":         (41.8781136, -87.6297982),
    "houston":      (29.7604267, -95.3698028),
    "休士頓":         (29.7604267, -95.3698028),
    "phoenix":      (33.4483771, -112.0740373),
    "鳳凰城":         (33.4483771, -112.0740373),
    "san francisco": (37.7792588, -122.4193286),
    "舊金山":         (37.7792588, -122.4193286),
    "seattle":      (47.6061389, -122.3328481),
    "西雅圖":         (47.6061389, -122.3328481),
    "boston":       (42.3600825, -71.0588801),
    "波士頓":         (42.3600825, -71.0588801),
    "washington":   (38.9071923, -77.0368707),
    "華盛頓":         (38.9071923, -77.0368707),
    "miami":        (25.7616798, -80.1917902),
    "邁阿密":         (25.7616798, -80.1917902),
    "las vegas":    (36.1699412, -115.1398296),
    "拉斯維加斯":       (36.1699412, -115.1398296),
    "toronto":      (43.6534817, -79.3839347),
    "多倫多":         (43.6534817, -79.3839347),
    "vancouver":    (49.2827291, -123.1207375),
    "溫哥華":         (49.2827291, -123.1207375),
    "montreal":     (45.5016889, -73.5672541),
    "蒙特婁":         (45.5016889, -73.5672541),
    "ottawa":       (45.4215296, -75.6971931),
    "渥太華":         (45.4215296, -75.6971931),
    "calgary":      (51.0447331, -114.0718831),
    "卡加利":         (51.0447331, -114.0718831),
    "edmonton":     (53.5461245, -113.4938229),
    "愛德蒙頓":        (53.5461245, -113.4938229),
    "mexico city":  (19.4326077, -99.1332340),
    "墨西哥城":        (19.4326077, -99.1332340),
    "guadalajara":  (20.6596988, -103.3496092),
    "瓜達拉哈拉":       (20.6596988, -103.3496092),
    "havana":       (23.1135925, -82.3665956),
    "哈瓦那":         (23.1135925, -82.3665956),
    "panama city":  (8.9936351, -79.5197177),
    "巴拿馬城":        (8.9936351, -79.5197177),
    "san jose":     (9.9281184, -84.0907246),
    "聖荷西":         (9.9281184, -84.0907246),
    "guatemala city": (14.6349149, -90.5068824),
    "瓜地馬拉城":       (14.6349149, -90.5068824),
    "tegucigalpa":  (14.0723403, -87.1921126),
    "德古斯加巴":       (14.0723403, -87.1921126),
    "managua":      (12.1148000, -86.2362000),
    "馬納瓜":         (12.1148000, -86.2362000),
    "santo domingo": (18.4860575, -69.9312117),
    "聖多明哥":        (18.4860575, -69.9312117),
    # ── 南美洲 ─────────────────────────────────────────────────────
    "sao paulo":    (-23.5505199, -46.6333094),
    "聖保羅":         (-23.5505199, -46.6333094),
    "rio de janeiro": (-22.9068467, -43.1728965),
    "里約熱內盧":       (-22.9068467, -43.1728965),
    "brasilia":     (-15.7934036, -47.8823172),
    "巴西利亞":        (-15.7934036, -47.8823172),
    "buenos aires": (-34.6036844, -58.3815590),
    "布宜諾斯艾利斯":     (-34.6036844, -58.3815590),
    "santiago":     (-33.4488897, -70.6692655),
    "聖地牙哥":        (-33.4488897, -70.6692655),
    "lima":         (-12.0463731, -77.0427934),
    "利馬":          (-12.0463731, -77.0427934),
    "bogota":       (4.7109887,  -74.0721372),
    "波哥大":         (4.7109887,  -74.0721372),
    "caracas":      (10.4805937, -66.9035723),
    "卡拉卡斯":        (10.4805937, -66.9035723),
    "quito":        (-0.2298500, -78.5249500),
    "基多":          (-0.2298500, -78.5249500),
    "la paz":       (-16.5000000, -68.1500000),
    "拉巴斯":         (-16.5000000, -68.1500000),
    "asuncion":     (-25.2867141, -57.6469811),
    "亞松森":         (-25.2867141, -57.6469811),
    "montevideo":   (-34.9011127, -56.1645314),
    "蒙特維多":        (-34.9011127, -56.1645314),
    "georgetown":   (6.8045186,  -58.1553452),
    "喬治敦":         (6.8045186,  -58.1553452),
    # ── 非洲 ──────────────────────────────────────────────────────
    "cairo":        (30.0444196,  31.2357116),
    "開羅":          (30.0444196,  31.2357116),
    "lagos":        (6.5243793,    3.3792057),
    "拉哥斯":         (6.5243793,    3.3792057),
    "johannesburg": (-26.2041028,  28.0473051),
    "約翰尼斯堡":       (-26.2041028,  28.0473051),
    "cape town":    (-33.9248685,  18.4240553),
    "開普敦":         (-33.9248685,  18.4240553),
    "nairobi":      (-1.2920659,   36.8219462),
    "奈洛比":         (-1.2920659,   36.8219462),
    "addis ababa":  (9.0319836,   38.7492254),
    "阿迪斯阿貝巴":      (9.0319836,   38.7492254),
    "casablanca":   (33.5731104,  -7.5898434),
    "卡薩布蘭加":       (33.5731104,  -7.5898434),
    "rabat":        (34.0209182,  -6.8415764),
    "拉巴特":         (34.0209182,  -6.8415764),
    "algiers":      (36.7372498,   3.0864900),
    "阿爾及爾":        (36.7372498,   3.0864900),
    "tunis":        (36.8190090,  10.1657470),
    "突尼斯":         (36.8190090,  10.1657470),
    "tripoli":      (32.8872094,  13.1913383),
    "的黎波里":        (32.8872094,  13.1913383),
    "khartoum":     (15.5006544,  32.5598994),
    "喀土穆":         (15.5006544,  32.5598994),
    "accra":        (5.6037168,   -0.1869644),
    "阿克拉":         (5.6037168,   -0.1869644),
    "abidjan":      (5.3599517,   -4.0082563),
    "阿必尚":         (5.3599517,   -4.0082563),
    "dakar":        (14.7167150, -17.4676861),
    "達卡":          (14.7167150, -17.4676861),
    "kinshasa":     (-4.4419311,  15.2662931),
    "金沙薩":         (-4.4419311,  15.2662931),
    "luanda":       (-8.8368200,  13.2343100),
    "羅安達":         (-8.8368200,  13.2343100),
    "kampala":      (0.3475964,   32.5825197),
    "坎帕拉":         (0.3475964,   32.5825197),
    "dar es salaam": (-6.1630100,  35.7515600),
    "三蘭港":         (-6.1630100,  35.7515600),
    "lusaka":       (-15.3875259,  28.3228165),
    "路沙卡":         (-15.3875259,  28.3228165),
    "harare":       (-17.8252306,  31.0335098),
    "哈拉雷":         (-17.8252306,  31.0335098),
    "maputo":       (-25.9692166,  32.5731752),
    "馬布多":         (-25.9692166,  32.5731752),
    "antananarivo": (-18.9249700,  47.5183870),
    "塔那那利佛":       (-18.9249700,  47.5183870),
    "abuja":        (9.0764785,    7.3985580),
    "阿布賈":         (9.0764785,    7.3985580),
    # ── 大洋洲 ─────────────────────────────────────────────────────
    "sydney":       (-33.8688197,  151.2092955),
    "雪梨":          (-33.8688197,  151.2092955),
    "melbourne":    (-37.8142176,  144.9631608),
    "墨爾本":         (-37.8142176,  144.9631608),
    "brisbane":     (-27.4697707,  153.0251235),
    "布里斯本":        (-27.4697707,  153.0251235),
    "perth":        (-31.9505269,  115.8604572),
    "伯斯":          (-31.9505269,  115.8604572),
    "adelaide":     (-34.9284989,  138.6007456),
    "阿得雷德":        (-34.9284989,  138.6007456),
    "auckland":     (-36.8484597,  174.7633315),
    "奧克蘭":         (-36.8484597,  174.7633315),
    "wellington":   (-41.2864603,  174.7761953),
    "威靈頓":         (-41.2864603,  174.7761953),
    "canberra":     (-35.2809368,  149.1300092),
    "坎培拉":         (-35.2809368,  149.1300092),
    "suva":         (-18.1415884,  178.4421662),
    "蘇瓦":          (-18.1415884,  178.4421662),
    "port moresby": (-9.4438004,   147.1802694),
    "莫爾斯比港":       (-9.4438004,   147.1802694),
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
            raw_pois = cached["raw_pois"]
        else:
            if city_key in _KNOWN_CITIES:
                lat, lon = _KNOWN_CITIES[city_key]
            else:
                location = MapAPI.geocode(city)
                lat, lon = location["lat"], location["lon"]
            raw_pois = MapAPI.fetch_poi_all(lat, lon)
            if raw_pois:
                _city_cache[city_key] = {"lat": lat, "lon": lon, "raw_pois": raw_pois}
            # Overpass 全失敗時 raw_pois=[]，padding 會填滿，不中斷

        treasures = _assign_tiers(raw_pois, lat, lon)

        # Pad to treasure_count with random positions when Overpass returns fewer POIs
        target = GAME_CONFIG["treasure_count"]
        cos_lat_pad = math.cos(math.radians(lat))
        _max_pad_m = 950  # slightly above max dist_m=900 to allow for clamping margin
        _pad_dlat = _max_pad_m / 111320.0
        _pad_dlon = _max_pad_m / (111320.0 * cos_lat_pad)
        idx = len(treasures)
        attempts = 0
        while len(treasures) < target and attempts < 300:
            attempts += 1
            angle = random.uniform(0, 2 * math.pi)
            dist_m = random.uniform(200, 900)
            nlat = lat + math.cos(angle) * dist_m / 111320.0
            nlon = lon + math.sin(angle) * dist_m / (111320.0 * cos_lat_pad)
            # clamp to a safe radius so padded treasures are always reachable
            nlat = max(lat - _pad_dlat, min(lat + _pad_dlat, nlat))
            nlon = max(lon - _pad_dlon, min(lon + _pad_dlon, nlon))
            if all(haversine((nlat, nlon), (t.lat, t.lon)) >= _MIN_TREASURE_SPREAD for t in treasures):
                treasures.append(Treasure(
                    id=f"t{idx}", name=f"神秘地點 {idx + 1}",
                    lat=nlat, lon=nlon, category="mystery", points=100
                ))
                idx += 1

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


@app.route("/rules")
def rules():
    return render_template("rules.html")


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
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@700;900&family=Noto+Sans+TC:wght@400;700&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#080E1C;display:flex;align-items:center;justify-content:center;
     height:100vh;font-family:"Noto Sans TC",sans-serif;color:#E6EDF3;
     background-image:url('/static/bg.png');background-size:cover;background-position:55% 62%}}
body::before{{content:'';position:fixed;inset:0;
     background:rgba(0,8,24,.62);pointer-events:none}}
.card{{position:relative;z-index:1;text-align:center;padding:40px 50px;
       background:#161B2E;border-radius:20px;
       border:1px solid rgba(56,139,253,.25);
       box-shadow:0 16px 52px rgba(0,0,0,.6),inset 0 1px 0 rgba(255,255,255,.04);
       max-width:340px;width:90%;backdrop-filter:blur(18px)}}
.spin{{width:52px;height:52px;border:4px solid rgba(56,139,253,.18);
       border-top-color:#388BFD;border-radius:50%;
       animation:spin .8s linear infinite;margin:0 auto 20px}}
@keyframes spin{{to{{transform:rotate(360deg)}}}}
.title{{font-family:"Orbitron",monospace;font-size:16px;font-weight:900;margin-bottom:18px;
        background:linear-gradient(90deg,#FFD700,#F0C000,#64B5F6);
        -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;
        letter-spacing:1px}}
.step{{font-size:14px;color:#F0C000;min-height:22px;margin-bottom:6px}}
.sub{{font-size:12px;color:#8B949E;min-height:18px;margin-bottom:20px}}
.err{{color:#ef5350;font-size:13px;display:none;margin-bottom:14px}}
.btn{{padding:9px 24px;border:none;border-radius:20px;cursor:pointer;
      font-size:13px;font-weight:bold;
      background:linear-gradient(135deg,#1565C0,#388BFD);color:#fff;display:none}}
</style>
</head>
<body>
<div class="card">
  <div class="title">🏙️ 準備 {city}</div>
  <div class="spin" id="sp"></div>
  <div class="step" id="st">🔍 搜尋附近景點與寶藏…</div>
  <div class="sub"  id="sb">連線地圖資料庫中…</div>
  <div class="err"  id="er"></div>
  <button class="btn" id="bt" onclick="location.href='/'">← 回首頁</button>
</div>
<script>
const ID='{req_id}';
const STEPS=['🔍 搜尋附近景點與寶藏…','📍 規劃最佳尋寶路線…','🗺️ 描繪城市輪廓與邊界…','⚔️ 即將出發！'];
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
