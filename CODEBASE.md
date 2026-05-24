# 拓樸拾遺錄 — 完整程式碼文件

> **最後更新：2026-05-24（v6.9）**
> **公開網址：https://treasure-hunt-lew0.onrender.com**
> **GitHub：https://github.com/timmyweistudy-design/treasure-hunt**（push master → Render 自動部署 2-3 分鐘）
> 每次修改任何檔案後，必須同步更新此文件。

---

## 目錄
1. [專案概覽](#1-專案概覽)
2. [資料夾結構](#2-資料夾結構)
3. [啟動方式](#3-啟動方式)
4. [遊戲設定](#4-遊戲設定)
5. [計分公式](#5-計分公式)
6. [後端路由](#6-後端路由)
7. [函式速查](#7-函式速查)
8. [技術架構筆記](#8-技術架構筆記)
9. [更新日誌](#9-更新日誌)

---

## 1. 專案概覽

| 項目 | 說明 |
|------|------|
| 語言 | Python 3 + HTML/CSS/JavaScript |
| 框架 | Flask（後端）+ Leaflet.js 1.9.4（地圖前端） |
| 外部 API | Nominatim（地理編碼）、Overpass（3鏡像並行，POI/建築）、OSRM（路線規劃） |
| 演算法 | TSP Brute-force（≤8點）+ Nearest-Neighbor + **2-opt 改善**（>8點）、Haversine、Ray-Casting 多邊形碰撞、A* 路徑規劃 |
| 字型 | Orbitron（數字/計時）、Noto Sans TC（中文） |
| 部署 | Render.com（免費方案，15分鐘無人使用後睡眠，冷啟動 30-50s） |
| 排行榜持久化 | GitHub Contents API（`scores.json` 存 repo，繞過 Render ephemeral 磁碟） |

### 遊戲流程
```
首頁（輸入名字+城市）
  → POST /start（背景執行）
    → 查 _KNOWN_CITIES 或呼叫 Nominatim 取得座標
    → Overpass 抓 POI（node-only 輕量查詢）
    → _assign_tiers() 分配 10 個寶藏到 5 距離環
    → solve_tsp_exact() + 2-opt 計算最優順序
    → 動態 bbox（起點+所有寶藏+20% margin，400~3000m 半徑）
  → 輪詢 /start/poll 直到 done
  → 進入 game.html（所有遊戲資料嵌入 JSON）
    → 背景從 Overpass 下載建築物（localStorage 快取 24h）
    → 建築載入後：buildNavGrid() + buildRouteGrid() + rebuildOptimalRouteAstar()
    → 3-2-1 倒數 → 開始
  → WASD 移動，Space 收集/傳送
    → POST /collect/<id>（含 order_bonus + combo + golden）
  → 時間到 or 全部收集 → GET /finish → 計算時間獎勵 → 存排行榜
```

---

## 2. 資料夾結構

```
timmy-agent/
├── app.py                  # Flask 主程式，所有路由 + 背景準備邏輯
├── config.py               # 全域常數（API URL、GAME_CONFIG）
├── CODEBASE.md             # ← 本文件
├── Procfile                # Render 啟動指令：web: python app.py
├── fly.toml                # Fly.io 設定（備用，目前部署在 Render）
├── requirements.txt        # pip 依賴
├── data/
│   └── scores.json         # 排行榜本機備份（Render 重部署後清空，以 GitHub 為主）
├── game/
│   ├── __init__.py
│   ├── map_api.py          # 所有外部 API 呼叫 + 伺服器端快取
│   ├── models.py           # Treasure / Player / Scoreboard dataclass + GitHub 持久化
│   └── pathfinder.py       # TSP + 2-opt + Haversine
├── static/
│   ├── bg.png              # 背景圖（地中海風格寶箱水彩）
│   ├── chest.png           # 寶箱 PNG（534×534 透明背景）
│   ├── thunder.mp3         # 雷聲音檔（CC0）
│   └── sprites/
│       ├── player/         # Arun1-6.png（跑步 6 幀）
│       ├── guard/          # Grun1-8.png（跑步）、Ghurt1-3.png（受傷）
│       ├── chaser/         # Crun1-6.png（跑步）、Churt1-2.png（受傷）、Cattack1-5.png（攻擊）
│       └── thief/          # Trun1-8.png（跑步）、Thurt1-3.png（受傷）
├── templates/
│   ├── index.html          # 首頁（輸入表單 + 排行榜）
│   ├── game.html           # 遊戲主畫面（4046行，含全部遊戲邏輯）
│   ├── finish.html         # 結算畫面（分數滾動動畫）
│   └── rules.html          # 規則說明頁
└── venv/                   # Python 虛擬環境
```

---

## 3. 啟動方式

### 本機（WSL2）
```bash
cd /mnt/c/Users/timmy/Downloads/timmy-agent
venv/bin/python app.py
# → Starting with waitress on port 5000...
# 瀏覽器：http://localhost:5000
```

### 雲端部署（Render.com）
```bash
git add -A
git commit -m "描述"
git push origin master
# Render 自動偵測 → 重新部署（約 2-3 分鐘）
```

> **注意：** 如果 `git push` 失敗（因排行榜 GitHub API 寫入導致落後），先執行 `git pull --rebase origin master` 再 push。

---

## 4. 遊戲設定

### config.py
```python
NOMINATIM_URL = "https://nominatim.openstreetmap.org"
OVERPASS_URL  = "https://overpass-api.de/api/interpreter"
OSRM_URL      = "https://router.project-osrm.org"

GAME_CONFIG = {
    "time_limit":      600,   # 遊戲時間（秒）= 10 分鐘
    "treasure_count":  10,    # 寶藏數量（固定 10 個，不足時以神秘地點補滿）
    "search_radius":   2000,  # POI 搜尋半徑（公尺，參考用）
    "collect_radius":  50,    # 收集範圍（公尺），WASD 走到附近按 Space 才能收集
    "time_bonus_rate": 1,     # 每剩 1 秒加幾分（最多 600×1=600）
    "categories": ["cafe", "museum", "park", "library", "restaurant"]
}
```

### game.html 前端常數（關鍵值）
| 常數 | 值 | 說明 |
|------|----|------|
| `NAV_CELL` | `0.00018`（≈20m） | AI A* 導航格大小 |
| `ROUTE_CELL` | `max(0.000025, bbox/360)`（≈2.8m） | 路線顯示 A* 格大小（細化至偵測3-5m透天厝） |
| `CLCT_R` | `50` | 收集半徑（公尺） |
| `CHASER_SPAWN_DELAY` | `30` | 第一隻追跡者出現時間（秒） |
| `CHASER_WAVE_INTERVAL` | `60` | 追跡者追加間隔（秒） |
| `CHASER_MAX` | `3` | 追跡者上限 |
| `PATROLLER_WAVE_INTERVAL` | `15` | 守衛追加間隔（秒） |
| `STUN_DURATION` | `1.5` | 被定身持續（秒） |
| `STUN_CD` | `5` | 定身冷卻（秒） |
| `STUN_R` | `30` | 守衛施放定身距離（公尺） |
| `GRENADE_CHARGES` | `2` | 手雷最大儲量 |
| `GRENADE_RECHARGE` | `20` | 手雷充能（秒） |
| `GRENADE_RADIUS` | `80` | 爆炸半徑（公尺） |
| `GRENADE_STUN_DUR` | `4` | 手雷暈眩時間（秒） |
| `MINE_CHARGES` | `2` | 地雷最大儲量 |
| `MINE_RECHARGE` | `25` | 地雷充能（秒） |
| `MINE_RADIUS` | `20` | 地雷觸發半徑（公尺） |
| `MINE_STUN_DUR` | `5` | 地雷暈眩時間（秒） |
| `MINE_LIFETIME` | `90` | 地雷自動消除（秒） |
| `GOLDEN_INTERVAL` | `45` | 黃金寶藏出現間隔（秒） |
| `GOLDEN_DURATION` | `15` | 黃金寶藏持續（秒） |
| `GOLDEN_MULT` | `3` | 黃金寶藏分數倍率 |
| `THIEF_WANTED_DUR` | `12` | 小偷通緝時間（秒） |
| `CATCH_R` | `80` | 抓小偷距離（公尺） |
| `ITEM_MAX` | `20` | 地圖上道具上限 |
| `ITEM_IVTL` | `1` | 道具生成間隔（秒） |
| `ITEM_LIFE` | `40` | 道具存在時間（秒） |
| `COMBO_WINDOW` | `22` | 連擊窗口（秒） |
| `DAY_CYCLE` | `150` | 日夜切換週期（秒） |
| `ORDER_BONUS` | `50` | 按最優順序收集加分 |

### 鍵盤快捷鍵一覽
| 按鍵 | 功能 |
|------|------|
| `W A S D` / 方向鍵 | 移動（可斜向） |
| `Shift` 長按 | 衝刺（×2，最多 10 秒） |
| `Space` | 收集寶藏 / 傳送門 |
| `1`–`5` | 切換道具槽 |
| 滾輪 | 循環切換道具槽 |
| `Q` | 使用當前道具 |
| `E` | 手雷瞄準（再按取消） |
| `F` | 埋地雷 |
| `R` | 丟誘餌 |
| `]` | 地圖放大 |
| `[` | 地圖縮小 |
| `Escape` | 取消手雷瞄準 |

---

## 5. 計分公式

```
總分 = 寶藏分 + 順序獎勵 + 連擊獎勵 + 黃金獎勵 + 時間獎勵 − AI扣分

寶藏分    = 各寶藏 points 值（= 該寶藏到起點的公尺距離，由 _assign_tiers 計算）
順序獎勵  = 按 OPTIMAL 順序收集每個 +50 分（最多 10×50 = 500 分）
連擊獎勵  = 22秒內連續收集：第2寶 +30、第3寶 +60、第4寶 +90…（(n-1)×30）
黃金獎勵  = 黃金寶藏持續期間收集：額外 +寶藏原分×(3-1)（即原分×2）
時間獎勵  = max(0, 600 − 實際用時) × 1（最多 600 分）
AI扣分    = 追跡者觸碰 −50 分（8秒冷卻）
           巡邏守衛觸發定身 −80 分
           小偷偷竊 −被竊寶藏分數
```

---

## 6. 後端路由

| 方法 | 路由 | 說明 |
|------|------|------|
| GET  | `/` | 首頁，顯示表單 + 排行榜 |
| GET  | `/rules` | 規則說明頁 |
| POST | `/start` | 啟動背景準備（geocode→POI→TSP→建築預取），回傳輪詢頁面 |
| GET  | `/start/poll` | 輪詢背景準備進度，完成後回傳 game_key |
| GET  | `/game` | 遊戲主頁（需 game_key query param），含 Cache-Control: no-store |
| GET  | `/roads` | 建築物多邊形（bbox 參數 s/n/w/e，有伺服器端快取） |
| POST | `/collect/<id>` | 收集寶藏，JSON `{"order_bonus": N}`（含順序+連擊+黃金獎勵合併） |
| POST | `/penalty` | AI 攻擊扣分，JSON `{"amount": N}` |
| POST | `/score_add` | 加分（用於逮捕小偷獎勵等），JSON `{"bonus": N}` |
| GET  | `/finish` | 結算，計算時間獎勵，存排行榜 |
| GET  | `/health` | 健康檢查（Render ping 用） |

---

## 7. 函式速查

### game/map_api.py

| 函式 | 說明 |
|------|------|
| `_haversine_m(a, b)` | 兩點直線距離（公尺） |
| `_spread_select(elements, count)` | 貪婪選取彼此間距最大的 POI |
| `_parallel_post(query, handler, ...)` | 並行 POST 至所有 Overpass 鏡像，回傳第一個成功結果 |
| `MapAPI.geocode(city_name)` | 城市名 → 座標（Nominatim），有 1req/s rate limit |
| `MapAPI.fetch_roads(lat, lon)` | 以單點為中心 900m 查詢建築物（備援） |
| `MapAPI.fetch_roads_focused(points, r)` | 多點小 bbox union 查詢（省 60-80% 資料量） |
| `MapAPI.fetch_roads_bbox(s, n, w, e)` | 完整遊戲邊界 bbox 查詢建築物（主要入口） |
| `MapAPI._parse_map_data(data)` | Overpass JSON → `{roads, buildings}` |
| `MapAPI.fetch_poi_all(lat, lon)` | node-only POI 輕量查詢；失敗走 Nominatim 備援 |
| `MapAPI._nominatim_poi_raw(lat, lon)` | Nominatim 關鍵字備援（8 種，每次 1.1s 間隔） |
| `MapAPI.get_route(coords)` | OSRM 步行路線座標（目前 route_coords_json 傳空陣列，路線由前端 A* 繪製） |

### game/pathfinder.py

| 函式 | 說明 |
|------|------|
| `haversine(a, b)` | 兩點 Haversine 距離（公尺） |
| `solve_tsp_nearest_neighbor(start, treasures)` | Greedy 最近鄰，O(n²)，作為大量寶藏的初始解 |
| `_two_opt(start, route)` | 2-opt 局部搜索：交換路段對直到無法改善，消除交叉路線 |
| `solve_tsp_exact(start, treasures)` | ≤8點：暴力枚舉最優解；>8點：nearest-neighbor + **_two_opt 改善** |
| `calculate_total_distance(start, route)` | 起點→路線各點 Haversine 總距離 |

### game/models.py

| 函式/類別 | 說明 |
|-----------|------|
| `rate_limit(calls_per_second)` | decorator，限制函式呼叫頻率（用於 Nominatim） |
| `_gh_load()` | 從 GitHub Contents API 讀取 scores.json → (scores, sha) |
| `_gh_save(scores, sha)` | 把 scores.json 寫回 GitHub（帶 SHA 防競態） |
| `Scoreboard.save_score(player, city)` | 新增分數，先 GitHub 後本機備份 |
| `Scoreboard.get_top10(city)` | 取得指定城市（或全部）前 10 筆 |
| `Treasure.to_dict()` | Treasure → 可序列化 dict |
| `Player.elapsed_time` | property，遊戲已用秒數 |

### templates/game.html（前端 JS）

#### 音效
| 函式 | 說明 |
|------|------|
| `getAudio()` | 初始化 AudioContext + 主音量鏈（Gain→Compressor→destination） |
| `snd(fn)` | 靜音保護執行音效 callback |
| `_dest()` | 回傳 masterOut（所有一般音效輸出節點） |
| `playThunder()` | 播放真實雷聲 MP3 + 閃電視覺（含首次解碼快取） |
| `_startAmbient(type)` | 開始環境音（晴天鳥聲/霧/雨） |
| `_stopAmbient()` | 停止所有環境音節點 |

#### 玩家移動 & 碰撞
| 函式 | 說明 |
|------|------|
| `tryMove(dLat, dLon)` | 嘗試移動玩家，軸分離滑牆 + 邊界夾擠；多步分解防止高速穿牆 |
| `isInBuilding(lat, lon)` | 判斷座標是否在任意建築多邊形內（空間 hash 加速） |
| `pointInPoly(lat, lon, coords)` | Ray-casting 多邊形碰撞（coords 格式：`[[lon,lat],...]`） |
| `ensureOutsideBuilding()` | BFS 找最近可走格子並傳送玩家（卡牆逃脫） |
| `buildingGrid` | 空間 hash（`GRID_DEG=0.001°`），加速 `isInBuilding` 查詢 |

#### 遊戲邏輯
| 函式 | 說明 |
|------|------|
| `collectNearest()` | Space 鍵：傳送門→逮捕小偷→撿道具→收集寶藏 |
| `collect(id, lat, lon)` | async，POST /collect/<id>，更新分數+視覺 |
| `applyScorePenalty(amt, msg)` | 扣分並同步後端 /penalty |
| `effectiveR()` | 當前有效收集半徑（廣域道具啟用時 ×3） |
| `useNearestPortal()` | 傳送玩家至最近傳送門的配對出口 |
| `updateDistances()` | 更新羅盤/HUD 距離；**全DOM元素皆快取**（不在每幀 getElementById） |

#### DOM 快取（啟動時建立，避免每幀查詢）
| 快取 | 內容 |
|------|------|
| `_compassArrowEl` | `#compass-arrow` |
| `_compassNameEl` | `#compass-name` |
| `_compassDistEl` | `#compass-dist` |
| `_tDomCache[t.id]` | 每個寶藏的 `{dEl, btn, card, ppD, ppBtn}` |
| `_dnCdEl/_dnIconEl/_dnPhaseEl` | 日夜徽章元素 |
| `_compassBoxEl` | 羅盤外框 |

#### 道具
| 函式 | 說明 |
|------|------|
| `spawnItem()` | 生成隨機道具（優先靠近未收集寶藏 300m 內） |
| `applyItem(type, id)` | 觸發道具效果（speed/star/range/freeze/magnet） |
| `tickPullingItems(dt)` | 磁鐵吸引動畫：飛行道具推近玩家 |
| `dropDecoy()` | 放置誘餌，轉移所有 AI 注意力 6 秒 |
| `tickDecoy(dt)` | 誘餌計時，到期重置 AI 路徑 |

#### 戰鬥
| 函式 | 說明 |
|------|------|
| `throwGrenade()` | 消耗手雷，55格飛行動畫，抵達後暈眩 80m 內 AI |
| `placeMine()` | 腳下放地雷（0.8s 武裝），踩中暈眩 AI |
| `tickGrenades(dt)` | 推進手雷飛行，管理充能計時 |
| `tickMines(dt)` | 偵測 AI 踩雷，管理充能計時 |
| `_stunAI(ai, dur)` | 設定 AI 暈眩：清路徑 + sprite 切換 hurt 幀 + ⭐ 旋轉標籤 |
| `_applyAIFilter(ai, filterStr)` | 冰凍/暈眩 filter 直接套在 `<img>` 幀（防灰框 bug） |
| `tickCombatStun(dt)` | 遞減暈眩計時，時間到恢復 sprite 並移除 ⭐ |
| `catchWantedThief()` | 逮捕通緝小偷，返還被盜分數 + 50 獎勵 |
| `_spawnExplosionVfx(lat, lon, radiusM)` | 地圖上建立爆炸環 DOM 動畫 |

#### AI
| 函式 | 說明 |
|------|------|
| `spawnAI(type, silent)` | 生成 AI（patroller/chaser/thief），隨機選無建築位置 |
| `tickChaser(ai, dt, s)` | 追跡者：A* 追玩家（或誘餌），觸碰扣分，時間壓力加速 |
| `tickPatroller(ai, dt, s)` | 巡邏守衛：沿 OPTIMAL 路標巡邏，FOV 偵測定身 |
| `tickThief(ai, dt, s)` | 小偷：追寶藏偷竊，隱身 5s/15s 冷卻，被通緝時逃跑 |
| `inPatrollerFOV(ai)` | 玩家是否在守衛長方形視野錐內（120m×40m） |
| `updateFOVPoly(ai)` | 重繪守衛視野多邊形 |
| `_thiefSetInvis(ai, on)` | 切換小偷隱形（marker/miniMarker/catchCircle 透明度） |
| `relocateTreasure(tId)` | 小偷把寶藏搬到新位置（同距離環隨機方向） |

#### 路徑規劃
| 函式 | 說明 |
|------|------|
| `buildNavGrid()` | AI 導航格（`NAV_CELL=0.00018`，≈20m），建築物載入後建一次 |
| `buildRouteGrid()` | 路線顯示精細格（`ROUTE_CELL≈0.00008`，≈9m），**只探中心點**（防密集住宅區細巷封死） |
| `runAstar(sLat,sLon,tLat,tLon)` | AI 用 A*（navGrid，vis≤3000） |
| `runRouteAstar(rg,fLat,fLon,tLat,tLon)` | 路線顯示 A*（routeGrid，vis≤100000），失敗退回空白格再試 |
| `snapToUnblocked(rg, lat, lon)` | BFS 找最近未被建築阻擋格子（路線端點吸附） |
| `smoothRoutePath(path, rg)` | Bresenham 視線判斷去除 A* 鋸齒（精確不漏建築） |
| `rebuildOptimalRouteAstar()` | 重算玩家→下一個寶藏路線；觸發時機：移動>12m、收集、小偷搬走 |
| `lineOfSightClearGrid(rg,r1,c1,r2,c2)` | Bresenham 格線視線判斷 |

#### 精靈動畫 & 視覺
| 函式 | 說明 |
|------|------|
| `_updateSpriteSize()` | 玩家精靈縮放（52px 基準，16-80px，zoom-aware） |
| `_updateGuardSizes()` | 所有守衛精靈縮放 |
| `_updateChaserSizes()` | 所有追跡者精靈縮放 |
| `_updateThiefSizes()` | 所有小偷精靈縮放 |
| `pushTrail(dt)` | 記錄玩家移動軌跡（最多60點，金色虛線） |
| `showToast(msg, dur)` | 右上角提示（dur=3000ms） |
| `showScoreFloat(lat, lon, gained)` | 寶藏位置浮出 +N 分動畫 |
| `spawnParticles(lat, lon)` | 收集寶藏時噴射粒子特效 |

#### 主迴圈 & 天氣
| 函式 | 說明 |
|------|------|
| `loop(ts)` | 主遊戲迴圈（rAF），try/catch 保護，永不中斷 |
| `tickWeather(dt)` | 天氣倒數，時間到切換；管理打雷間隔 |
| `setWeather(type)` | 切換 sunny/fog/storm，更新覆蓋層+音效 |
| `_checkDayNight()` | 每秒檢查日夜切換（每150s）；只在值改變時寫DOM |
| `updateDistances()` | 更新羅盤方向+距離+寶藏清單 HUD（使用預快取DOM元素） |
| `updateMiniMap()` | 更新小地圖玩家+AI 位置 |

---

## 8. 技術架構筆記

### 城市座標快取（_KNOWN_CITIES）
`app.py` 中硬編碼 **250+ 城市座標**（英文+中文名各一），完全跳過 Nominatim 呼叫，防止 429 錯誤。

涵蓋地區：
- **台灣**：全 17 縣市（台北/台中/台南/高雄/新竹/桃園/基隆/苗栗/彰化/南投/雲林/嘉義/屏東/宜蘭/花蓮/台東/澎湖）
- **日本**：東京/大阪/京都/名古屋/札幌/福岡/廣島/橫濱
- **中國**：北京/上海/廣州/深圳/成都/重慶/武漢/南京/杭州/西安/天津/澳門
- **韓國/東南亞**：首爾/釜山/仁川/香港/新加坡/曼谷/雅加達/吉隆坡/胡志明市/河內/馬尼拉/仰光/金邊/永珍
- **南亞/中亞/西亞**：孟買/新德里/加爾各答/班加羅爾/喀拉蚩/伊斯蘭馬巴德/可倫坡/加德滿都/達卡/德黑蘭/巴格達/利雅德/杜拜/多哈/安卡拉/伊斯坦堡/耶路撒冷等
- **歐洲**：巴黎/倫敦/柏林/阿姆斯特丹/羅馬/馬德里/里斯本/維也納/布魯塞爾/斯德哥爾摩/奧斯陸/哥本哈根/赫爾辛基/華沙/布拉格/布達佩斯/雅典/莫斯科/基輔等 40+
- **北美**：紐約/洛杉磯/芝加哥/休士頓/舊金山/西雅圖/波士頓/華盛頓/邁阿密/拉斯維加斯/多倫多/溫哥華/蒙特婁/渥太華/墨西哥城等
- **南美**：聖保羅/里約熱內盧/巴西利亞/布宜諾斯艾利斯/聖地牙哥/利馬/波哥大等
- **非洲**：開羅/拉哥斯/約翰尼斯堡/開普敦/奈洛比/阿迪斯阿貝巴/卡薩布蘭加/阿爾及爾/阿克拉/金沙薩等
- **大洋洲**：雪梨/墨爾本/布里斯本/伯斯/坎培拉/奧克蘭/威靈頓

未知城市才呼叫 Nominatim（有 `@rate_limit(1req/s)` 保護）。

### A* 路徑規劃（兩套格子）

| | AI 導航（navGrid） | 路線顯示（routeGrid） |
|--|--|--|
| 格子大小 | `NAV_CELL=0.00018`（≈20m） | `ROUTE_CELL≈0.00008`（≈9m） |
| 格子建立 | 建築載入後，`isInBuilding(center)` | 建築載入後，只探中心點 |
| A* 預算 | vis ≤ 3000 | vis ≤ 100,000 |
| 對角線防角穿 | ✅ | ✅ |
| 路徑平滑 | — | Bresenham 視線 smoothRoutePath |
| 失敗 fallback | [] (AI 等待重算) | 空白格 A* 再試，仍失敗才直線 |

**密集住宅區問題（已修）：**
- 舊版用 5 點探測（center ±4m），台灣透天厝 3-5m 巷道被相鄰建築封死
- 現版只探 center，巷道格子可通行

### TSP 算法
- ≤8 個寶藏：暴力 permutation，保證最優
- 10 個寶藏（固定）：Greedy Nearest-Neighbor → **2-opt 局部搜索**
  - 2-opt 交換路段對消除路線交叉，可縮短 5-20% 總距離
  - 0.5m 容差防浮點數死循環
  - 多輪迭代直到無法改善

### 建築物載入流程
```
loadBuildingsBackground()
  → fetchBuildingsCached()  (localStorage bld4_* key，24h 有效)
    → fetchBuildingsDirect() (並行 POST 3個 Overpass 鏡像，10s timeout)
  → loadBuildings(raw)       (建立 buildings[] + buildingGrid hash)
  → relocatePortalsFromBuildings()
  → yield (setTimeout 0)
  → buildRouteGrid()
  → yield
  → rebuildOptimalRouteAstar()
  → yield
  → L.geoJSON 繪製建築多邊形
  → ensureOutsideBuilding()
```

### 幀節流
| 類型 | 頻率 | 執行內容 |
|------|------|----------|
| 每幀（60fps） | rAF | 玩家移動、碰撞、相機 lerp、tick 函式 |
| `uiFrame`（15fps） | 每4幀 | DOM 更新（距離、minimap、天氣、AI chip） |
| `aiFrame`（30fps） | 每2幀 | AI marker setLatLng |

### DOM 快取策略
- `_tDomCache`：10個寶藏的 5 個 DOM 元素各快取一次（原每 UI frame 50+ getElementById）
- `_compassArrowEl/_compassNameEl/_compassDistEl`：羅盤 3 元素快取
- `_dnCdEl/_dnIconEl/_dnPhaseEl`：日夜徽章快取
- `tickItems` 的 `item._badgeEl`：道具 badge 快取

### AI Sprite 系統
- 所有 AI 類型使用 DOM display 切換（`classList add/remove 'active'`），不用 `img.src` 切換（防空白閃爍）
- Filter 直接套在 `<img>` 幀而非外層 div（防 GPU 合成層灰框 bug）
- 縮放公式：`Math.round(52 * Math.pow(2, zoom-17))`，clamp 16–80px

### 排行榜持久化
```
Scoreboard.save_score()
  → _gh_save(scores, sha)  →  GitHub Contents API PUT（帶 sha 防競態）
  → 本機 data/scores.json 備份（失敗靜默）
  → 下次讀取：_gh_load() 優先，失敗回 data/scores.json
```
需在 Render 環境變數設 `GITHUB_TOKEN=ghp_...`

---

## 9. 更新日誌

### 2026-05-24（v6.9）Debug Console + 小偷移位同步 + 全面改名

**Debug Console `window.dbg`（game.html 底部）**
- 密碼保護：`dbg.unlock(密碼)` 才能使用其他指令；密碼以 XOR 混淆儲存，不以明文出現在原始碼
- 瀏覽器 F12 → Console 解鎖後輸入 `dbg.help()` 列出全部指令
- 天氣：`dbg.sunny/fog/storm()`；日夜：`dbg.day()/night()`
- 傳送：`dbg.tp(lat,lon)` / `dbg.goto(N)`（第N個寶藏）
- 時間：`dbg.setTime(秒)` / `dbg.addTime(秒)`
- AI：`dbg.spawnChaser/Guard/Thief()` / `dbg.stunAll(秒)` / `dbg.killAll()`
- 道具啟用：`dbg.speed/star/range/magnet/freeze()`
- 武器：`dbg.refillGrenade/Mine/Decoy/Sprint/All()`
- 寶藏：`dbg.golden()` / `dbg.collectAll()` / `dbg.listTreasures()`
- 查詢：`dbg.status()`

### 2026-05-24（v6.8）小偷移位同步 + Folium 標註 + 全面改名

**小偷移位座標同步（`relocateTreasure` → session）**
- 問題：`relocateTreasure()` 在 JS 端更新 `t.lat/t.lon`，但 `/collect` POST 只送 `order_bonus`，server session 座標從未更新 → Folium 結算地圖標在原始位置
- `game.html`：`relocateTreasure()` 設 `t.wasMoved = true`；`collect()` POST 多帶 `lat`, `lon`, `was_moved`
- `app.py` `/collect/<id>`：讀取 `lat/lon/was_moved` 並寫入 `session["treasures"]` 對應項目
- `_build_finish_map()`：`was_moved` 寶藏的 Folium Marker 邊框改橙紅（`#FF6B35`），popup 加「🦹 曾被小偷移位」標註

**遊戲更名**
- 全專案 "地圖尋寶大冒險" → **"拓樸拾遺錄"**（templates + CODEBASE.md）

### 2026-05-22（v6.7）路線+效能+TSP 全面優化

**路線穿牆修正（buildRouteGrid）**
- 舊：5 點探測（center ±ROUTE_CELL×0.45≈4m）；台灣密集透天厝 3-5m 巷道被相鄰建築的邊緣探測封死 → A* 找不到路 → 直線穿牆
- 新：**只探 center 點**；細巷格子恢復可通行
- A* 預算：32,000 → **100,000**（密集城區繞路需要更大搜索量）
- 失敗 fallback：直線 → **空白格 A* 再試**，至少給彎曲方向而非直線穿牆

**AI 導航格縮小（buildNavGrid）**
- `NAV_CELL`：0.0004（≈44m）→ **0.00018（≈20m）**
- AI 追跡者/守衛在密集住宅區穿牆情況改善

**2-opt TSP（pathfinder.py）**
- 新增 `_two_opt(start, route)`：後處理交換路段對
- `solve_tsp_exact` 超過 8 點時：greedy → 2-opt
- 路線不再交叉，總距離縮短 5-20%

**DOM 快取完整版（game.html）**
- 新增 `_compassArrowEl/_compassNameEl/_compassDistEl`
- 新增 `_tDomCache`：10個寶藏×5個元素，啟動時快取
- `collect()` 和 `updateDistances()` 全改用快取，消除每秒 150+ 次 getElementById

**nearTreasure O(2n) → O(n)**
- 道具生成時找最近寶藏：原本 reduce 跑兩次 → 改為單次迴圈

**台灣縣市座標擴充（app.py _KNOWN_CITIES）**
- 新增新竹/基隆/桃園/苗栗/彰化/南投/雲林/嘉義/屏東/宜蘭/花蓮/台東/澎湖
- 搜尋這些城市不再觸碰 Nominatim，無 429 風險

**rules.html 數值全面同步**
- 巡邏守衛扣分 -30 → **-80**；追跡者 -50 → **-100**；小偷 -20 → **-50**
- 追跡者首次出現 60s → **30s**；守衛新增波次說明（每15s+1隻，上限20隻）
- 天氣機制：「每60秒切換持續30秒」→ **晴天55-65s，霧/雷雨25-45s不重複**
- 定身補充具體時間：1.5秒，冷卻5秒
- 順序獎勵補充全程上限 +500 分

**結算頁 Folium 地圖（finish.html + app.py）**
- 新增依賴：`folium==0.20.0`、`branca==0.8.2`（requirements.txt）
- 新增 `_build_finish_map(player_data, treasures_data, optimal_order)` → Folium 地圖 HTML
  - CartoDB Positron 底圖、自動 fit_bounds
  - 🟡 金色實線：玩家實際收集順序路線
  - 🔵 藍色虛線：TSP 建議最佳路線
  - 金色數字標記（已收集）+ 灰色 ✕ 標記（未收集），點擊顯示 popup（名稱、分數）
- `finish_game()` 生成 Folium HTML，失敗時 fallback `None`（不影響結算頁其他內容）
- `finish.html` 以 `iframe srcdoc`（透過 `tojson` 注入）嵌入地圖，隔離 CSS/JS 衝突

**OSRM 步行距離計分（app.py + map_api.py）**
- 新增 `MapAPI.get_walking_distances(origin, destinations)` — 呼叫 OSRM `/table/v1/walking/` 一次取得全部距離，fallback Haversine
- `_bg_prepare` 在 padding 完成後呼叫，更新每顆寶藏 `t.points = OSRM步行公尺數`
- 神秘地點（padding）也一併更新，不再固定 100 分
- 比直線距離高約 20–40%，河流/高架區域差異更大

**地圖縮放快捷鍵修正（game.html）**
- 移除 `=`/`+`/`-` 縮放快捷鍵（丟手雷時誤觸連發造成地圖瞬間放到最大 zoom 19）
- 改用 `]` 放大、`[` 縮小，遠離 WASD/數字/武器鍵區，不會誤觸
- rules.html 同步更新快捷鍵說明

**全球城市座標大擴充（app.py _KNOWN_CITIES → 250+ 條目）**
- 補齊現有西方城市中文名：紐約/洛杉磯/雪梨/墨爾本/巴黎/倫敦
- 新增亞洲：日本（名古屋/札幌/福岡等）、中國（北京/上海/廣州/深圳等12城）、韓國（釜山/仁川）、東南亞（雅加達/吉隆坡/胡志明市等）、南亞（孟買/新德里/加爾各答/班加羅爾）
- 新增中東：杜拜/利雅德/德黑蘭/伊斯坦堡/耶路撒冷/安卡拉等
- 新增歐洲：柏林/羅馬/馬德里/維也納/布魯塞爾/斯德哥爾摩/莫斯科/基輔等 40+ 城市
- 新增美洲：芝加哥/休士頓/舊金山/西雅圖/多倫多/溫哥華/墨西哥城/聖保羅/布宜諾斯艾利斯等
- 新增非洲：開羅/拉哥斯/約翰尼斯堡/奈洛比/卡薩布蘭加等
- 新增大洋洲：布里斯本/伯斯/坎培拉/奧克蘭/威靈頓等
- 所有城市均提供英文+中文兩種拼法，任意輸入均命中快取

---

### 2026-05-22（v6.6）凍結 filter bug + DOM 快取（日夜）

- `_applyDayNight` setTimeout 未取消，快速切換時疊加 → 加 `_dnTimeout` clearTimeout
- 日夜徽章 DOM 快取：`_dnCdEl/_dnIconEl/_dnPhaseEl`，只在值有變動時寫 textContent
- `document.getElementById('map')` 在手雷模式每次觸發重查 → 快取至 `_mapEl`

---

### 2026-05-21（v5.x — v6.5）視覺主題 + Sprite 系統 + 戰鬥系統

**視覺主題（crimson/gold 統一）**
- 主底色 `#080408`、緋紅 `#C2185B`、金色 `#F4A020`
- `static/bg.png`（地中海風寶箱水彩）套用到所有頁面
- `static/chest.png`（534×534 透明背景寶箱）取代 emoji
- 全站字色統一提亮（深酒紅 → 可讀灰粉）

**Sprite 系統**
- 4 種角色（玩家/守衛/追跡者/小偷）各有跑步/受傷幀
- DOM display 切換（不用 img.src，防閃爍）
- Filter 套在 `<img>` 幀本身（防灰框 bug）
- 縮放感知 fps（onScreenPx 計算，zoom 連動幀率）

**戰鬥系統**
- 手雷（E）：2顆/20s充能，爆炸 80m 暈眩 4s
- 地雷（F）：2個/25s充能，20m 觸發暈眩 5s，90s 自動消除
- 小偷通緝：偷寶藏後 12s 內按 Space 在 80m 內可逮捕，返還分數 +50

**其他系統**
- 任意門（4個，對角配對）
- 黃金寶藏（45s 出現，15s 持續，×3 倍率）
- 日夜切換（150s 一次）
- 天氣系統（晴/霧/雷雨，音效+視覺）
- 5格道具槽（speed/star/range/freeze/magnet）
- 連擊系統（22s 窗口，(n-1)×30 分）

---

### 2026-05-20（v4.x）AI 改良 + 寶藏系統重構

- 10 個寶藏，分 5 距離環（各 2 個，分數 = 到起點公尺數）
- `_assign_tiers()`：按距離分層，dot-product 選對邊方向
- 寶藏不足時自動補「神秘地點」（padding 邏輯）
- AI 全面改走 A* 路徑（不再直線移動），`requestIdleCallback` 非同步
- AI 牆壁滑動修正（軸分離 `aiMove()`）
- 小偷隱身（5s/15s冷卻）
- FOV 守衛視野（120m×40m 長方形）
- 動態 bbox（最遠寶藏+20% margin，400-3000m）
- 磁鐵吸引飛行動畫、手雷距離上限視覺
- 建築碰撞：全 bbox Overpass 查詢，localStorage 24h 快取

---

### 2026-05-19（v1.x - v3.x）基礎建設

- Flask + Leaflet 架構建立
- Render.com 雲端部署（Procfile + waitress）
- GitHub API 排行榜持久化
- 幀節流（uiFrame 15fps / aiFrame 30fps）
- 按鍵系統（lowercase 統一，clearAllKeys on blur/focus）
- 玩家移動軸分離滑牆（`tryMove`）
- 建築物碰撞（Ray-casting，空間 hash 加速）
- A* 路線顯示（細格，routeGrid）+ 視線平滑
- 相機指數 lerp（k=40）
- Leaflet marker 浮點位置更新（防整數像素跳格）
- CartoDB tile（比 OSM 快，台灣友好）
- 音效系統（Web Audio API，Master Gain+Compressor）

---

*本文件由 Claude Code 維護。如有遺漏請在對話中指出。*
