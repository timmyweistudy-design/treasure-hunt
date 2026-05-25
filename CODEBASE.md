# 拓樸拾遺錄 — 完整程式碼文件

> **最後更新：2026-05-25（v7.10.4）**
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
| 字型 | ThenKhung（標題，本地字型）、Orbitron（數字/計時）、Noto Sans TC（中文內文） |
| 部署 | Render.com（免費方案，15分鐘無人使用後睡眠，冷啟動 30-50s） |
| 排行榜持久化 | GitHub Contents API（`scores.json` 存 repo，繞過 Render ephemeral 磁碟） |
| 成就持久化   | GitHub Contents API（`achievements.json` 存 repo，按玩家名稱分組） |

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
│   ├── scores.json         # 排行榜本機備份（Render 重部署後清空，以 GitHub 為主）
│   └── achievements.json   # 成就本機備份（同上，以 GitHub 為主）
├── game/
│   ├── __init__.py
│   ├── map_api.py          # 所有外部 API 呼叫 + 伺服器端快取
│   ├── models.py           # Treasure / Player / Scoreboard / AchievementStore + GitHub 持久化
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
│   ├── index.html          # 首頁（輸入表單 + 排行榜 + 成就入口）
│   ├── game.html           # 遊戲主畫面（含成就追蹤 JS + _finishGame）
│   ├── finish.html         # 結算畫面（新解鎖成就展示 + 成就頁連結）
│   ├── achievements.html   # 成就樹視覺頁（SVG 連線 + 玩家查詢 + 進度條）
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
| POST | `/game_stats` | 前端送出本局成就統計（ai_encounter/bomb_hit 等），暫存於 session |
| GET  | `/finish` | 結算，計算時間獎勵，運算成就解鎖，存排行榜 + 成就 |
| GET  | `/achievements` | 成就樹頁面，`?player=名稱` 查詢玩家進度 |
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
| `Scoreboard.save_score(player, city)` | 新增分數，先 GitHub 後本機備份；同名玩家只保留最佳紀錄（分高優先，同分取用時短者） |
| `Scoreboard.get_top10(city)` | 取得指定城市（或全部）前 10 筆；同名玩家只保留最高分（按名稱去重） |
| `Scoreboard.get_by_city(top_n)` | 回傳 `[(city, [entries])]`，每城市前 top_n 名，城市依榜首分數降序排列 |
| `Treasure.to_dict()` | Treasure → 可序列化 dict |
| `Player.elapsed_time` | property，遊戲已用秒數 |
| `_gh_ach_load()` | 從 GitHub 讀取 achievements.json → ({data}, sha)，404 時回 ({}, None) |
| `_gh_ach_save(achs, sha)` | 寫回 GitHub achievements.json（帶 SHA 防競態） |
| `AchievementStore.get_player(name)` | 取得指定玩家成就字典（副本） |
| `AchievementStore.save_player(name, achievements)` | 更新玩家成就，先 GitHub 後本機備份 |
| `AchievementStore.get_all_players()` | 取得全部玩家成就資料 |

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
| `collect(id, lat, lon)` | async，POST /collect/<id>，更新分數+視覺；記錄夜間收集 & 連擊成就 |
| `applyScorePenalty(amt, msg)` | 扣分並同步後端 /penalty；同時設定 `_achDmgTaken=_achAIEncounter=true` |
| `effectiveR()` | 當前有效收集半徑（廣域道具啟用時 ×3） |
| `useNearestPortal()` | 傳送玩家至最近傳送門的配對出口；設 `_achPortalUsed=true` |
| `updateDistances()` | 更新羅盤/HUD 距離；**全DOM元素皆快取**（不在每幀 getElementById） |
| `_finishGame()` | async，送出 `/game_stats` POST（含所有成就追蹤數據），再 `location.href='/finish'`；防雙重呼叫 |

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
- **v7.7 新增**：HUD 完整快取（36 元素）—— `_chipSpeedEl`, `_sprintFillEl`, `_sprintLblEl`, `_sprintGlowEl`, `_vScoreEl`, `_timeVigEl`, `_chipAiEl`, `_aiDistEl`, `_aiCountTxtEl` 等；`tickEffects` / `tickSprint` / `tickAI` 的 `document.getElementById()` 全部消除
- **v7.7 新增**：玩家 sprite 快取 —— `_pfsCache`（`.pf` NodeList）、`_pswCache`（`#psw`）在 `pMarker.on('add')` 中建立

### AI Sprite 系統
- 所有 AI 類型使用 DOM display 切換（`classList add/remove 'active'`），不用 `img.src` 切換（防空白閃爍）
- Filter 直接套在 `<img>` 幀而非外層 div（防 GPU 合成層灰框 bug）
- 縮放公式：`Math.round(52 * Math.pow(2, zoom-17))`，clamp 16–80px
- **v7.7 新增**：`spawnAI` 生成後立即在 `ai._spr` 快取 NodeLists（`gf/ghurt/gsw`、`cf/churt/cattack/csw`、`tf/thurt/tsw`），`tickAI` sprite 迴圈直接使用，消除每幀 `querySelectorAll`（守衛最多 20 次、追跡者最多 3 次、小偷最多 3 次）

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

### 2026-05-25（v7.10.4）排行榜修正
- **app.py**：`get_by_city(top_n=5)` → `top_n=10`，每城市最多顯示 10 名
- **finish.html**：`.me td` 移除 `color: #D4920A !important`，只保留背景底色；避免 `!important` 蓋掉金/銀/銅排名色

---

### 2026-05-25（v7.10.3）排行榜金銀銅全色覆蓋
- **index.html + finish.html**：前三名加 `td b` color override，確保分數數字也跟著變色；銀色改 `#C0C8D2`（冷調銀），銅色改 `#C8803C`（暖銅）；三名皆加 `font-weight:600`；左側邊線顏色同步飽和

---

### 2026-05-25（v7.10.2）排行榜 CSS 完全統一
- **finish.html**：移除多餘的 `td:nth-child(4,5){ color:#484F58 }` 規則，確保表格字色與 index.html 逐行相同；`td:first-child` 屬性順序對齊

---

### 2026-05-25（v7.10.1）精緻化 14 項收尾

**game.html — 7 項：**
1. **標題漸層色對齊新色盤** — `.hd-title` 漸層 `#FFD700→#F0C000→#64B5F6` 改 `#C8920A→#D4920A→#3A7FD5`
2. **Header 底邊中性化** — `border-bottom rgba(56,139,253,.25)` 改 `rgba(255,255,255,.08)`
3. **Header stat 間格線** — `.hd-stats gap:22px` 改為 `gap:0` + 每個 `.stat` 加左側 `border-left: 1px solid rgba(255,255,255,.1)` + padding
4. **道具槽 selected 去外發光** — 改用 `border-bottom: 2px solid #D4920A` 底線指示 + inset 頂部反光，移除 `box-shadow: 0 0 14px` 外發光；移除 `backdrop-filter:blur`；`border-radius 10→6px`
5. **Leaflet popup 圓角** — `12px → 8px`；border 改中性 `rgba(255,255,255,.1)`
6. **Loading 卡片** — `border-radius 20px → 14px`；border 改中性 `rgba(255,255,255,.1)`
7. **card h2 顏色** — `#F0C000 → #D4920A`（index.html + finish.html，與新色盤統一）

**achievements.html — 2 項：**
8. **進度條移除 glow** — `.prog-fill box-shadow` 刪除；漸層改 `#C8920A→#D4920A→#3A7FD5`
9. **節點完成標記** — `.ach-badge` 移除 `box-shadow: 0 0 8px`，改 `border: 1.5px solid rgba(255,215,0,.55)`；背景色改 `#D4920A`

**finish.html — 3 項：**
10. **hero p font-weight 300** — 與 index.html 統一
11. **新成就卡片 + 徽章圓角** — `.new-ach-card 12→8px`；`.ach 20→10px`
12. **計分說明 hint** — 加 `border-left` 左邊線 + 淡底色，視覺層次感（出處注釋風格）

**index.html — 2 項：**
13. **guide-card hover 修正** — `:hover` 不再跑回藍色；只加深背景，各卡左邊框主題色保持
14. **排行榜前三名左邊線** — `tbody tr:nth-child(1/2/3)` 改用 `border-left: 3px solid [金/銀/銅色]` 指示，對齊整體「邊線語言」；同步套用至 finish.html

---

### 2026-05-25（v7.10）美術方向重塑 — 去 AI 感，回歸大型遊戲手繪質感

**設計原則：** 消除過度發光特效，採用「沉穩暗色 + 暖金 + 導航藍」三色節制用色；白天/夜晚呈現完全不同的排版結構感，而非僅換色。

**game.html — 10 項：**
1. **色盤重整**：黃金色從 `#FFD700/#F0C000` 統一收斂至 `#D4920A`；藍色從 `#388BFD` 收斂至 `#3A7FD5`；剔除多餘發光 box-shadow
2. **Sidebar 面板質感**：`.sb` 改為 `rgba(14,20,36,.97)` 深藍底 + `rgba(255,255,255,.06)` 微邊；滾動條細化至 3px；`.sb-foot` / `.kbd-box` 同步調整邊框
3. **鍵盤 key 樣式**：`.key` 使用半透明底 + 雙層邊框（底邊略厚），模擬實體按鍵立體感
4. **SVG 針式羅盤擴展**：viewBox 從 `-10 -18 20 36` 擴展為 `-22 -22 44 44`（寬 40px），加外圈 + N/S/E/W 四條刻度線；移除 `filter:drop-shadow`
5. **寶藏卡片角切設計**：`.tc` 改 `clip-path: polygon(10px 0, 100% 0, 100% 100%, 0 100%, 0 10px)` 左上角斜切；漸層從上至下；移除 `box-shadow`；`.tc.found` 以 `max-height:66px` 折疊
6. **效果 Chip 系統化**：`.eff-chip` 改暗底 + 左側色條（`border-left: 3px solid var(--ca)`）；每個 chip 以 CSS 變數 `--ca` 設定顏色，白天模式直接 override 變數
7. **sec-lbl 雙模式排版**：夜晚 = 底線分隔（技術感）；白天 = `border-left:3px solid` 左側邊線（野帳/日誌感），結構上的版式差異
8. **Toast 消除藍光**：`border-radius: 24px → 16px`；移除 `0 0 0 1px rgba(56,139,253,.08)` 藍色外輪廓
9. **日夜徽章收斂**：`border-radius: 20px → 10px`，與整體圓角風格統一
10. **白天模式卡片加重**：`body.day .tc .nm` font-weight 升至 900（反差對比，模擬手寫標注感）；`.eff-chip` 白天改為暖紙色底 + 各色文字

**finish.html — 3 項：**
11. **卡片圓角收斂**：`.card`、`.map-card` 從 `20px → 16px`；統一視覺語言
12. **統計格圓角收斂**：`.stat`（及 `.inner-shimmer`）從 `14px → 10px`
13. **總分字型層級**：`.stat-total .num` 放大至 `clamp(1.8rem, 5.5vw, 2.4rem)`；其餘三格收窄至 `1.5rem`，形成明確視覺主次

**achievements.html — 2 項：**
14. **根節點八角形**：`.ach-node.branch-root` 加 `clip-path: polygon(14% 0%,86% 0%,100% 14%,100% 86%,86% 100%,14% 100%,0% 86%,0% 14%)`，根節點呈八角形，區隔於普通方形節點
15. **節點圓角收斂**：`.ach-node` 從 `14px → 10px`

**index.html — 1 項：**
16. **Hero 副標 font-weight**：`.hero p` 加 `font-weight: 300`，關鍵字（`.h-city/.h-treas/.h-enemy/.h-rank`）保持 700，形成輕重對比

---

### 2026-05-25（v7.9.1）小修正
- **index.html**：移除排行榜冠軍行光掃動畫（item 20）
- **app.py**：`sprint_legend`（疾風傳說）解鎖門檻 5000m → **10000m（10km）**；同步更新成就描述文字

---

### 2026-05-25（v7.9）視覺美化 — 19 項精緻化

**game.html — 11 項：**
1. **SVG 針式羅盤**：羅盤指針從文字 `↑` 換成 SVG 菱形針（上紅下白，中心白圓點，藍光 drop-shadow），CSS `rotate()` 依然有效；`.compass-box.thief-alert` 時針尖轉橘色
2. **標頭標題光掃**：`.hd-title` 加 `display:inline-block` + `::after` 白光掃過動畫（3.5s 循環）
3. **進度條流動光紋**：`.prog-fill::after` 橫向流動光帶（2.4s linear 循環），光紋被 `overflow:hidden` 限制在填充寬度內
4. **已收集卡片折疊**：`.tc` 加 `max-height:180px; overflow:hidden`；`.tc.found` 設 `max-height:66px`，收集後卡片以 0.3s cubic-bezier 平滑折疊，隱藏距離列與按鈕
5. **道具槽 hover 回饋**：`.slot-box:hover` 加 `scale(1.07) + brightness(1.22)`（0.15s transition）
6. **底部 HUD 漸層光邊**：移除 1px 實線 `border-top`，改用 `#bottom-hud::before` 偽元素繪製左右漸淡藍光帶
7. **衝刺啟動閃光**：`tickSprint` 在 `isSprinting&&!wasSprinting` 時觸發 `.sprint-fill.flash`（白光掃 0.38s 動畫），`void offsetWidth` 強制重繪確保可重觸發
8. **載入畫面背景漂移**：`#loading-overlay` 加 `@keyframes bg-drift`（`background-position` 55%62% ↔ 58%60%，18s alternate），等待畫面不再靜止
9. **充能格增強光暈**：`.c-pip.on` 改為 `radial-gradient` + 雙層 `box-shadow`（白光核心 + 青藍暈）
10. **玩家脈衝三段色變**：`@keyframes ppulse` 從單色藍改為 `#1565C0 → #388BFD → #90CAF9` 三段色彩呼吸
11. **日間模式羅盤 SVG 配色**：`body.day #compass-arrow polygon:first-child` 深紅、`:last-child` 深棕半透明

**finish.html — 4 項：**
12. **計分 easeOutBack 超衝**：`step()` 改用 `easeOutBack(c1=1.70158)` 函式，分數計數超衝 ~10% 後彈回目標值，結束設精確值
13. **總分格脈衝邊框**：`.stat-total` 加 `total-score-pulse` keyframe animation（2s delay 在 entry shimmer 後啟動，2.4s 循環）
14. **新成就入場金光**：`@keyframes ach-unlock` 在 75% 處加入 `scale(1.06)` 超衝 + `box-shadow:0 0 26px rgba(255,215,0,.72)`，落定後自然消散
15. **英雄標題底部光暈**：`.hero h1::after` 偽元素，`radial-gradient(ellipse)` 金色環境光暈置於標題正下方

**achievements.html — 3 項：**
16. **已解鎖節點呼吸光暈**：三組 keyframes（`ach-breathe-gold/red/teal`）配合各分支顏色，以 2.2~2.8s 循環動態呼吸
17. **連線強化**：已解鎖路徑 `stroke-width` 提升至 2.8，加 `filter:drop-shadow` 發光；未解鎖路徑 `stroke-opacity:0.5` + 保持虛線
18. **Tier 分隔標籤裝飾**：`.tier-label` 改 flex 佈局，`::before/::after` 各加金色漸淡橫線

**index.html — 2 項：**
19. **指南卡片彩色左邊框**：六張指南卡各設 3px 彩色左邊框（金/藍/紅/綠/橘/淡藍，對應卡片主題）
20. **排行榜冠軍行光掃**：`tbody tr:nth-child(1)::after` 金色光帶 3.8s 循環橫掃第一名行

---

### 2026-05-25（v7.8）Bug 修正：黃金圈殘留 + 成就樹拖拉捲動

**game.html — 黃金寶藏圓圈殘留（已修）：**
- 根因：`relocateTreasure(tId)` 移動寶藏時，`goldenRing`（Leaflet circle）位置不跟著更新，導致黃色圓圈停在舊位置，直到玩家採集才因 `clearGoldenTreasure` 順帶移除
- 修法：`relocateTreasure` 更新 `t.lat/t.lon` 後，若 `tId===goldenId` 則立即 `goldenRing.setLatLng([nLat,nLon])`，使圓圈跟隨寶藏移動

**achievements.html — 左鍵拖拉捲動（新增）：**
- `.tree-outer` 加 `cursor:grab` + `.dragging` class（`cursor:grabbing`）
- `mousedown/mousemove/mouseup` 事件：拖拉距離 >3px 才算拖拉（保留節點點擊），`scrollLeft` 跟隨滑鼠位移更新
- 觸碰裝置保留原生觸控行為，不干擾

---

### 2026-05-25（v7.7）效能全面優化

**game.html — 9 項優化：**

1. **`distM()` 改平面近似（最高優先）** — Haversine（`sin²/atan2`，12次三角/開方）→ 平面直角近似（1次 cos + 1次 sqrt）。精度差 < 0.5%（3km 內），遊戲計算全部 < 3km，35+ 個 call site 全受益。
2. **AI sprite NodeList 快取（`ai._spr`）** — `spawnAI` 生成後立即 `querySelectorAll` 存入 `ai._spr`，`tickAI` 守衛/追跡者/小偷三段各省一次 DOM 遍歷。最多 26 AI 時每 AI frame 省 26 × 3 = 78 次查詢。
3. **`patrollerCount` 計數器** — 新增 `let patrollerCount=0`，取代 4 處 `aiList.filter(a=>a.type==='patroller').length` O(n) 掃描；`spawnAI` patroller 分支 `patrollerCount++`；`killAll()` 重設為 0。
4. **HUD 36 個元素完整快取** — `tickEffects` / `tickSprint` / `tickAI` 全部 `getElementById` 改用啟動時建立的 const 快取；每 UI frame（15fps）省約 36 次 DOM 查詢。
5. **玩家 sprite 快取** — `_pfsCache`/`_pswCache` 在 `pMarker.on('add')` 建立，主迴圈 & `_updateSpriteSize` 優先用快取。
6. **`_scheduleRouteRebuild()` debounce** — 新增 `clearTimeout` 模式函式；收集寶藏、小偷移位兩個 `setTimeout(rebuildOptimalRouteAstar,50)` 改呼叫此函式，防短時間內雙重排程。
7. **`tickAI` `chip-ai` 改用快取** — 首幀 init 的 `getElementById('chip-ai')` 改用 `_chipAiEl`。
8. **`v-score` 3 處改用快取** — `catchWantedThief`、`applyScorePenalty`、`collect()` 全改用 `_vScoreEl`。
9. **`time-vignette` 改用快取** — 主迴圈每 UI frame 的 `getElementById('time-vignette')` 改用 `_timeVigEl`。

**achievements.html — 1 項優化：**
- 移除 `.tree-outer` 的 `scroll→drawLines` 監聽器 — SVG 線段位置相對於 `tree-wrap`，水平捲動不改變相對座標，只有 `resize` 才需要重繪。

**app.py — 2 項優化：**
- `_cleanup_game_data()` 背景線程 — 每 5 分鐘掃描 `_game_data`，清除 `start_time` 超過 10 分鐘的殭屍條目，防止記憶體洩漏。
- `compute_new_achievements()` 本地變數提前提取 — 12 個常用 `game_stats.get()` 呼叫（`max_combo`、`thief_catch_count` 等）提前到函式頭部存為局部變數，消除重複查詢。

---

### 2026-05-25（v7.6）11 個新成就 + 追蹤鉤全面擴充

**app.py — 新增 11 個成就：**

| ID | 名稱 | Tier | Branch | 解鎖條件 |
|----|------|------|--------|---------|
| `sprint_first` | 破風初試 💨 | 2 | amber | 首次使用衝刺 |
| `lightning_start` | 迅雷開場 ⚡ | 2 | amber | 遊戲開始 5 秒內收集第一個寶藏 |
| `sprint_legend` | 疾風傳說 🌪️ | 3 | amber | 一局衝刺累計距離 ≥ 5000m |
| `last_moment` | 最後一刻 ⏱️ | 3 | amber | 剩餘 ≤ 30 秒時收集最後一個寶藏 |
| `perfect_concert` | 完美協奏 🎵 | 3 | amber | 一局同時獲得順序加分、連擊加分、黃金加分 |
| `iron_guardian` | 百折不撓 💪 | 3 | amber | 被守衛定身 10 次以上仍完美通關 |
| `all_weapons` | 全副武裝 ⚔️ | 3 | red | 一局中使用手雷、地雷與誘餌 |
| `swift_catch` | 神速逮捕 🏃 | 3 | red | 通緝令發出 3 秒內逮捕小偷 |
| `stun_master` | 暈眩製造者 😵 | 3 | red | 一局讓敵人暈眩累計 20 次 |
| `portal_warrior` | 傳送奇兵 🌀 | 3 | teal | 傳送後 5 秒內收集寶藏 |
| `magnet_master` | 磁吸大師 🧲 | 3 | teal | 磁鐵一次吸收 5 個以上道具 |

**app.py — ACHIEVEMENT_PARENTS 新增：**
- `sprint_first` → `first_treasure`（amber tier 2）
- `lightning_start` → `first_treasure`
- `sprint_legend` → `sprint_first`（amber tier 3）
- `last_moment` → `perfect_clear`
- `perfect_concert` → `first_combo`
- `iron_guardian` → `perfect_clear`
- `all_weapons` → `mine_first`（red tier 3）
- `swift_catch` → `iron_will`
- `stun_master` → `first_bomb`
- `portal_warrior` → `first_portal`（teal tier 3）
- `magnet_master` → `all_items`

**app.py — ACHIEVEMENT_TIERS 更新：**
- Tier 2 amber 新增：`sprint_first`、`lightning_start`
- Tier 3 amber 新增：`sprint_legend`、`last_moment`、`perfect_concert`、`iron_guardian`
- Tier 3 red 新增：`all_weapons`、`swift_catch`、`stun_master`
- Tier 3 teal 新增：`portal_warrior`、`magnet_master`

**game.html — 新增 14 個追蹤變數（成就追蹤批次擴充）：**
| 變數 | 說明 |
|------|------|
| `_achSprintUsed` | 是否使用過衝刺 |
| `_achSprintTotalDist` | 衝刺累計距離（公尺估算，SPRINT_SPD×111111×dt） |
| `_achFirstTreasureTime` | 第一個寶藏收集時的遊戲已耗時（秒，-1=未收集） |
| `_achLastTreasureRemain` | 最後寶藏收集時的倒數剩餘（秒） |
| `_achGuardStunCount` | 被敵人定身次數（chaser + patroller 各自計） |
| `_achWantedStartTime` | 小偷進入通緝時的 `performance.now()`（ms） |
| `_achQuickCatch` | 是否在通緝令發出 3 秒內逮捕 |
| `_achTotalStuns` | 讓敵人暈眩累計次數（手雷+地雷 hit 數） |
| `_achPortalTime` | 使用傳送門的 `performance.now()`（ms） |
| `_achPortalQuickCollect` | 傳送後 5 秒內是否收集寶藏 |
| `_achMagnetPickupCount` | 當次磁鐵已吸收道具數 |
| `_achMagnetMaxPickup` | 單次磁鐵最多吸收道具數 |
| `_achGotOrderBonus` | 本局是否獲得至少一次順序加分 |

**game.html — 追蹤鉤注入位置：**
- 移動區塊 `if(dx||dy)`：`isSprinting` 時累加 `_achSprintTotalDist`，設 `_achSprintUsed`
- `tickGrenades` `hit>0`：`_achTotalStuns += hit`
- `tickMines` `mineHit>0`：`_achTotalStuns += mineHit`
- `tickChaser` stun 觸發：`_achGuardStunCount++`
- `tickPatroller` stun 觸發：`_achGuardStunCount++`
- `tickThief` 小偷偷竊後：`_achWantedStartTime = performance.now()`
- `catchWantedThief`：檢查 3s 差距，設 `_achQuickCatch`，重設 `_achWantedStartTime=-1`
- `useNearestPortal`：`_achPortalTime = performance.now()`
- `_activateItem('magnet')`：重設 `_achMagnetPickupCount=0`
- 主迴圈磁鐵區塊 `pullingItems.set()`：`_achMagnetPickupCount++`，更新 Max
- `collect()` 成功後：記錄 `_achFirstTreasureTime`、`_achPortalQuickCollect`、`_achGotOrderBonus`
- `collect()` win 判斷前：`_achLastTreasureRemain = remaining`

**game.html — `_finishGame` payload 新增欄位：**
`sprint_used`, `sprint_total_dist`, `first_treasure_time`, `last_treasure_remain`, `guard_stun_count`, `quick_catch`, `total_stuns`, `portal_quick_collect`, `magnet_max_pickup`, `got_order_bonus`

---

### 2026-05-25（v7.5）成就樹排版重整 + 地雷範圍傷害 + 8 新成就 + 雜項修正

**app.py — ACHIEVEMENT_TIERS 重排（按顏色分群）：**
- Tier 1：amber（💎初獲寶藏）| red（⚔️初遇敵人）| teal（🎒道具嘗鮮）
- Tier 2：amber×3（完美/連擊/黃金初嚐）| red×3（初試爆破/鋼鐵/地雷）| teal×3（全能/傳送/聲東）
- Tier 3：amber×8（閃電/高分/夜行…）| red×3（爆破/神探/地雷伏擊）
- Tier 4：amber×3（極速/黃金神話/狂神）
- 新增 8 個成就：黃金初嚐🌟 初埋地雷💣 聲東擊西🪤 黃金狂熱✨ 地雷伏擊🕳️ 絕對路線🧭 極速傳說⚡ 連擊狂神🔥
- 新增 3 個成就（上版）：鐵血神探🕵️ 風雨無阻⛈️ 黃金神話👑

**game.html — 地雷改為範圍傷害：**
- `tickMines`：移除 `break`，掃描半徑內所有 AI 全數暈眩，顯示命中數量（與手雷同邏輯）
- 新增追蹤變數：`_achGoldenCollected/Count`、`_achMineHit/MaxMineSimulHit`、`_achDecoyUsed`、`_achWeatherCollect`

**finish.html — 數字截斷修正：**
- shimmer 動畫移至 `.inner-shimmer` 子層，`.stat` 改 `overflow:visible`
- `.stat .num` 改 `letter-spacing:0` + `font-size:clamp(1.35rem,4.5vw,2rem)`

**achievements.html — 水平滾動修正：**
- 加 `.tree-outer`（`overflow-x:auto`）+ `.tree-wrap`（`min-width:max-content`）
- 修正 `justify-content:center` 在溢出容器左側無法捲到的問題
- 加第 5 層標籤「傳說層」

### 2026-05-25（v7.4）成就系統

**game/models.py：**
- 新增 `_gh_ach_load/save()`：同 Scoreboard 模式，讀寫 GitHub `achievements.json`
- 新增 `AchievementStore` 類別：per-player 成就字典 `{player_name: {ach_id: bool}}`，GitHub 優先 + 本機備份

**app.py：**
- 新增 `ACHIEVEMENT_DEFS`（16 成就定義：名稱/emoji/描述/tier/branch）
- 新增 `ACHIEVEMENT_PARENTS`（parent→child 樹狀依賴）、`ACHIEVEMENT_TIERS`（4 層排列）
- 新增 `compute_new_achievements(existing, game_stats, ...)`：依本局統計解鎖成就，回傳新解鎖 ID 列表
- 新增路由 `POST /game_stats`：接收前端遊戲統計，暫存至 `session["game_stats"]`
- 新增路由 `GET /achievements`：渲染成就樹頁（`?player=名稱` 查詢）
- 修改 `/finish`：讀取並清除 `session["game_stats"]`，計算並儲存成就，傳 `new_achievements`/`ach_defs` 給模板

**templates/game.html：**
- 新增 11 個成就追蹤變數（`_achAIEncounter/DmgTaken/ItemTypesUsed/BombHit/MaxSimulHit/PortalUsed/ThiefCaught/GotCombo/MaxComboCount/NightCollect`）
- 6 個函式注入追蹤鉤：`applyScorePenalty`、`_activateItem`、`tickGrenades`（炸彈命中計數）、`useNearestPortal`、`catchWantedThief`、`collect`（連擊/夜間收集）
- 新增 `_finishGame()` async 函式：POST stats → await → redirect；防雙送旗標 `_finishStarted`
- 所有遊戲結束跳轉（勝利/時間到/結束按鈕）改呼叫 `_finishGame()`

**templates/finish.html：**
- 新增成就卡區塊 CSS（`ach-unlock` 彈入動畫）
- 若有新解鎖成就：展示每個成就的 emoji+名稱+描述卡（依次延遲彈入）
- 底部加「查看完整成就樹」/ 「查看成就進度」連結

**templates/index.html：**
- 規則連結旁新增「🏅 成就」導覽連結（`.ach-nav-link` 金色樣式）

**templates/achievements.html（新建）：**
- 深色主題成就樹頁面：玩家名稱搜尋表單、進度條（X/16）
- 4 層 tier row + flexbox 節點卡（unlocked/locked 各色 glow/灰度）
- JS 在 load 後以 SVG bezier 曲線繪製 parent→child 連線（已解鎖彩色實線/未解鎖灰色虛線）
- 支援行動裝置（水平捲動）

### 2026-05-25（v7.3）視覺精緻化 Round 3

**game.html：**
- 讀取 spinner：border spinner → 彗星光弧 + 同心圓光暈
- 讀取城市標題：ThenKhung + 金藍漸層
- 進度條：加 prog-header（標籤+Orbitron 數字 x/10），高度 5→7px，glow 填充
- 結束遊戲按鈕：加危險紅光脈動動畫
- 迷你地圖：加外發光 glow
- 天氣 chip：依天氣類型套色（sunny/fog/storm），JS 改用 className 不用 inline style
- 連擊 chip：金色 + 脈動 glow 動畫
- 充能格子：●● 改為 CSS `.c-pip` 圓形格子（filled/empty 各自樣式）
- 已收集寶藏卡：`.tc.found .nm` 加刪除線

**index.html：**
- 冒險指南：ul 重排為 2×3 icon card grid（hover 浮起）
- 排行榜前3名：各加金/銀/銅漸層行背景
- Hero 副標題關鍵詞配色（真實城市=藍、寶藏=金、敵人=紅、排行榜=綠）

**finish.html：**
- 再次出發按鈕：藍色→金色 + shimmer，與首頁出發按鈕統一
- 結算成就徽章：完美探索家/精銳冒險者/初心探索者/繼續磨練 + 閃電冒險 + 高分獵人

### 2026-05-25（v7.2）視覺精緻化 Round 2

- `game.html`：Toast 滑入 + 彈跳動畫、效果 Chip 各色彩徽章（夜/日雙模式）、Leaflet 縮放按鈕暗色主題覆寫
- `rules.html`：ThenKhung 標題、浮動動畫、section 卡片入場 + hover 發光、item-card hover 浮起、自訂滾動條

### 2026-05-25（v7.1）標題字型換為 ThenKhung

- `static/fonts/ThenKhung-Regular.ttf`：新增本地字型（來源：github.com/MoonlitOwen/ThenKhung）
- `templates/index.html`：`@font-face` 載入 ThenKhung，`.hero h1` 套用此字型，fallback 為 Noto Serif TC
- 移除 Ma Shan Zheng（不支援繁體字）

### 2026-05-24（v7.0）Bug 修正：Popup DOM 快取 + 小偷標示位置

**Bug 1：`_tDomCache` 的 ppD/ppBtn 永遠是 null（已修）**
- Leaflet popup DOM 在首次開啟時才建立，game init 時 `getElementById('pp-dist-/pp-btn-xxx')` 回傳 null
- 影響：彈窗中的距離顯示永遠不更新、收集後彈窗按鈕不變成「✅ 已收集」
- 修法：`_tDomCache` 移除 ppD/ppBtn 欄位；`updateDistances()` 改 live `getElementById`；`collect()` 改 live getElementById（popup 未開時自然回 null 跳過）

**Bug 2：小偷偷走寶藏後 🦹 地圖標示停在原位（已修）**
- `_updateThiefMarker()` 只在 `targetTId` 改變時才更新位置，同一目標被移位後標示凍結
- 修法：`relocateTreasure()` 中更新 `t.lat/lon` 後，立即對所有以此 ID 為目標的小偷呼叫 `ai.targetMarker.setLatLng([nLat,nLon])`

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
