# 地圖尋寶大冒險 — 完整程式碼文件

> **最後更新：2026-05-20（戰鬥系統 + VFX修正）**
> **公開網址（永久）：https://treasure-hunt-lew0.onrender.com**
> **GitHub：https://github.com/timmyweistudy-design/treasure-hunt**（push master → Render 自動部署）
> 每次修改任何檔案後請同步更新此文件。

---

## 目錄
1. [專案概覽](#1-專案概覽)
2. [資料夾結構](#2-資料夾結構)
3. [啟動方式](#3-啟動方式)
4. [遊戲設定（config.py）](#4-遊戲設定)
5. [計分公式](#5-計分公式)
6. [後端路由總覽](#6-後端路由總覽)
7. [完整程式碼](#7-完整程式碼)
   - [config.py](#configpy)
   - [app.py](#apppy)
   - [game/models.py](#gamemodelsry)
   - [game/pathfinder.py](#gamepathfinderpy)
   - [game/map_api.py](#gamemap_apipy)
   - [templates/index.html](#templatesindexhtml)
   - [templates/game.html](#templatesgamehtml)
   - [templates/finish.html](#templatesfinishhtml)
8. [技術架構筆記](#8-技術架構筆記)

---

### 2026-05-20 戰鬥系統 VFX/顯示修正

**爆炸環位置修正**
- `_spawnExplosionVfx(lat,lon,radiusM)`：改用 `left:pt.x-pxR; top:pt.y-pxR`，不再用 `transform:translate(-50%,-50%)`
- 根本原因：inline transform 與 keyframe `transform:scale(0→1)` 衝突，環跑到左上角
- 接受 `radiusM` 參數：地雷爆炸用 `MINE_RADIUS`，手雷用 `GRENADE_RADIUS`

**觸發範圍視覺化**
- 手雷：投擲後在落點顯示橘色虛線圓（80m），抵達時移除
- 地雷：放置後在腳下顯示紅色虛線圓（20m），觸發時移除

**AI 顏色恢復修正**
- `_stunAI`：改用 `el.style.filter='saturate(0) brightness(1.5)'`（直接 inline style）
- 舊方法 `[class$="-dot"]` 選擇器在 `class="patrol-dot alert"` 時失效
- stun 結束：`el.style.filter = aiFrozenTimer>0?'hue-rotate...':''`（保持凍結色）
- freeze 結束：`el.style.filter = ai.combatStun>0?'saturate...':''`（保持暈眩色）

---

### 2026-05-20 戰鬥系統（手雷 + 地雷 + 小偷反制）

**新增按鍵**
- `E` — 💣手雷：2顆儲量，充能 20s/顆；向最後移動方向投出約 200m，到達後爆炸 80m 內所有 AI 暈眩 4s
- `F` — 💥地雷：2個儲量，充能 25s/個；放置在玩家腳下，首個踏入 20m 的 AI 暈眩 5s 並觸發爆炸移除
- `Space`（擴充）— 小偷偷竊後 8 秒內按 Space，若距離 ≤30m 可逮捕，找回扣分 +50 獎勵

**新增函式（templates/game.html）**
- `throwGrenade()` — 消耗手雷，建立飛行中手雷物件（55 格動畫），抵達後呼叫 `_spawnExplosionVfx` + `_stunAI`
- `placeMine()` — 消耗地雷，建立地雷 marker（0.8s 武裝延遲），觸發時爆炸暈眩
- `tickGrenades(dt)` — 每幀推進手雷飛行動畫，並管理充能計時器
- `tickMines(dt)` — 每幀偵測 AI 踩雷，並管理充能計時器
- `catchWantedThief()` — 逮捕通緝小偷，返回 true 表示成功
- `tickCombatStun(dt)` — 遞減所有 AI 的 `combatStun` 計時器，清除暈眩樣式 + 管理 `wantedTimer`
- `_stunAI(ai, dur)` — 設定 `ai.combatStun=dur`，清空路徑，加 `ai-stunned` CSS class
- `_spawnExplosionVfx(lat,lon)` — 地圖上建立爆炸環 DOM 動畫

**新增常數**
- `GRENADE_CHARGES=2, GRENADE_RECHARGE=20, GRENADE_RADIUS=80, GRENADE_STUN_DUR=4`
- `MINE_CHARGES=2, MINE_RECHARGE=25, MINE_RADIUS=20, MINE_STUN_DUR=5`
- `THIEF_WANTED_DUR=8, CATCH_R=30`

**AI 新增欄位**（所有型別）
- `combatStun:0` — 暈眩剩餘秒數；>0 時 tickChaser/tickPatroller/tickThief 立即 return
- `wanted:false, wantedTimer:0` — 通緝狀態；小偷偷竊後設 true，8s 內玩家可逮捕
- `stolenAmt:0` — 被盜分數（供逮捕時還給玩家）

**HUD 新增**
- `chip-grenade`（常駐）：💣 ●● 顯示儲量，充能中顯示倒數秒
- `chip-mine`（常駐）：💥 ●● 顯示儲量，充能中顯示倒數秒
- `chip-wanted`：🚨 通緝！Xs 按Space！（小偷偷竊後 8 秒顯示）

---

### 2026-05-20 動態邊界 + 移動再優化

**動態正方形邊界（恰好框住最遠寶藏）**
- `app.py`：計算每個寶藏到起點的 Chebyshev 距離（m），取最大值 ×1.20 作為 half_m
- 限制 400m–3000m，確保遊戲體驗不會過大或過小

**移動更絲滑**
- 相機從 threshold(0.5px) 改回 lerp k=40：每幀移動 <0.2px（連續微移比大跳更滑）
- pCircle 回 60fps（每幀更新）
- `pMarker.on('add')` 設 `willChange:'transform'`，瀏覽器提前建立 GPU compositing layer
- `L.map` 加 `zoomAnimation:false, fadeAnimation:false, markerZoomAnimation:false`：
  關閉 Leaflet 內建動畫，避免每幀 `setView` 觸發動畫中斷造成卡頓

---

### 2026-05-20 2.5km×2.5km 邊界 + 移動絲滑根本修復

**邊界縮為 2.5km×2.5km**
- `app.py`：half = 1250m

**移動真正絲滑（根本原因修復）**
- 根本原因：Leaflet `latLngToLayerPoint` 內部呼叫 `.round()` 強制整數像素；zoom 17 下玩家每幀移動 0.39px，整數化後每 2-3 幀才動 1px → 一格一格
- `pMarker.update` 覆寫為浮點版本：`project(latlng) - pixelOrigin`（不 round）→ CSS `transform: translate3d(x.xxpx, y.yypx, 0)` 支援小數，視覺連續
- 相機改 pixel-distance threshold（>0.5px 才 setView）：只在實際需要時觸發 Leaflet DOM 重排，加 `noMoveStart:true` 省事件開銷
- pCircle（SVG 半徑指示）降至 30fps（`aiFrame`），省無謂 SVG 重繪

---

### 2026-05-20 路徑繞建築 + 鏡頭絲滑 + 全域優化

**最佳路徑完全繞開建築**
- `runRouteAstar`：A* 對角步加側邊格檢查，禁止切穿建築角落（diagonal corner-cutting fix）
- `runAstar`（AI 路徑）：同樣加入側邊格檢查
- `runRouteAstar` vis 上限 16000 → 32000（5km×5km 全圖可達）
- 新增 `lineOfSightClear()` + `smoothRoutePath()`：A* 後以視線判斷去除鋸齒中間點，路線更自然

**走路/跑步絲滑**
- `camLat/camLon` 平滑鏡頭變數（指數 lerp，τ≈0.056s）
- `tryMove` 移除 `map.setView`（不再每幀 snap Leaflet DOM）
- 主迴圈統一計算 camLat/camLon lerp 後才呼叫 `map.setView`，避免鋸齒感

---

### 2026-05-20 固定 5km×5km 邊界 + 全區建築碰撞（完整版）

**邊界永遠是 5km×5km 正方形**
- `app.py`：`half_lat = 2500 / 111320`、`half_lon = 2500 / (111320 × cos(lat))`
  - 以玩家起點為中心，形狀固定不變

**邊界內所有房子都有碰撞（完整）**
- `game.html`
  - `_parseOSMBuildings` 移除建築上限（原 3000→5000→無上限），確保全區覆蓋
  - Overpass query 加 `out body qt;`（空間排序）代替 `out body;`，建築物按地理位置均勻返回
  - query timeout 30s、fetch 超時 33s（5km×5km 資料量較小）
  - 快取版本號 `bld3_` → `bld4_`（強制重新拉取新格式）

---

### 2026-05-19 程式碼整理

- 刪除 `game/map_renderer.py`（folium 舊渲染器，已由 Leaflet.js 取代，無任何呼叫）
- 移除 `requirements.txt` 未使用依賴：`folium`, `branca`, `xyzservices`, `numpy`
- `game/models.py`：移除死碼 `log_action` decorator 與 `Player.collect_treasure()` 方法；import 移至頂部
- 從 git 移除根目錄 `scores.json`（stale 副本，正確路徑為 `data/scores.json`）

---

## 1. 專案概覽

| 項目 | 說明 |
|------|------|
| 語言 | Python 3 + HTML/CSS/JavaScript |
| 框架 | Flask（後端）、Leaflet.js（地圖前端） |
| 外部 API | Nominatim（地理編碼）、Overpass（POI / 建築物）、OSRM（路線規劃） |
| 演算法 | TSP 精確解（≤8 點 brute-force permutations）、Haversine 距離、Ray Casting 多邊形碰撞、A* 路徑規劃 |
| 平台 | WSL2（Flask 需 `host="0.0.0.0"`，瀏覽器用 WSL2 IP:5000） |
| 字型 | Google Fonts：Orbitron（數字/分數/計時/距離）、Noto Sans TC（中文介面） |

### 2026-05-19 移動 bug 修復：對角線 + 卡頓（最新）

**對角線移動只走單一方向（`tryMove` 碰撞判斷順序 bug）**
- 根本原因：`else` 分支先執行 `if(dLat){pLat=cLat}` 更新了 `pLat`，再用*新* `pLat` 測試 lon 碰撞，導致 Y 位移影響 X 碰撞判斷
- 修正：先以原始 `pLat/pLon` 計算兩軸碰撞結果（`moveLat`, `moveLon`），再一起套用

**持續按住移動鍵卡頓（main thread 被建築物計算阻塞）**
- 根本原因：`loadBuildingsBackground()` 連續同步呼叫 `loadBuildings()` → `buildRouteGrid()` → `rebuildOptimalRouteAstar()`，阻塞主執行緒數百 ms，rAF 無法插入執行
- 修正：三個重計算之間加入 `await new Promise(r=>setTimeout(r,0))` 讓出主執行緒

---

### 2026-05-19 game.html 玩家邊界 & 飄移修復

**玩家不可走出 BOUNDS 邊界（多層）**
- `tryMove()` 加入 `clampToBounds(lat, lon)`，每次移動前夾在 `BOUNDS.s/n/w/e` 內
- `ensureOutsideBuilding()` 候選位置也先 clamp 再使用，堵住無敵結束後的逃脫路徑
- 主迴圈每幀硬夾 `pLat/pLon`：任何程式路徑都無法讓玩家超出邊界

**幽靈按鍵飄移（其他玩家）**
- `keydown` 最前方加 `if(!gameReady) return`：倒數期間完全不記錄按鍵
- `keydown` 加 `if(e.isComposing||e.key==='Process') return`：攔截中文輸入法（IME）假事件
- `startCountdown()` 在 `gameReady=true` 前呼叫 `clearAllKeys()`：清除倒數累積的殘留按鍵
- **根本原因修復**：所有單字元鍵統一用 `_nk(k)` 轉小寫後儲存
  - Shift+W → keydown `e.key='W'` → 存 `'w'`；放開 W（Shift 已放）→ keyup `e.key='w'` → 刪 `'w'` ✓
  - 原本大小寫不一致：存 `'W'` 但刪 `'w'`，導致 `keys['W']` 永遠殘留飄移
  - CapsLock 切換造成的大小寫不一致也同步修復
- 主迴圈每幀掃描移動鍵：超過 **500ms** 無 keydown 重整即視為放開（原 3000ms 太慢）
  - keydown repeat 約每 33ms 觸發，500ms ≈ 15 次重整，ghost key 在 <0.5s 內消失
- `keyDownAt[key]` 每次 keydown（含 repeat）都更新，確保合法持鍵不被誤清
- 伺服器延遲 **不會** 導致飄移；移動邏輯 100% 在前端 JS 執行

---

### 2026-05-19 game.html 建築物碰撞 & 地圖修復（最新）

**白屏根本原因：`let astarBudget` 重複宣告**
- 第 1763 與 1842 行各宣告一次，瀏覽器拋 `SyntaxError: Identifier already declared`，整個 `<script>` 停止執行 → Leaflet 地圖從未初始化 → 白屏
- 修正：刪除第二個重複宣告

**地圖 tile 來源換為 CartoDB**
- 從 `tile.openstreetmap.org` 改為 `basemaps.cartocdn.com/rastertiles/voyager`（Fastly 全球 CDN，台灣載入速度更快）
- tile 失敗時自動 fallback 回 OSM
- `#map` 加 `background: #e8edf4` 防止 tile 未載入時純白

**Leaflet 載入失敗偵測**
- 主 script 最前方加 `typeof L === 'undefined'` 檢查
- 若 Leaflet 未載入：overlay 顯示錯誤 + retry 按鈕，且不會被 10 秒 failsafe 強制關掉
- `_showErr()` 修改為同時恢復 overlay 顯示，防止錯誤被隱藏

**建築物碰撞覆蓋：整個遊玩邊界**
- Overpass 查詢從「焦點點小圓」改為「`BOUNDS` 正方形 bbox」一次抓全區
  ```
  way["building"](s,w,n,e)
  ```
  maxsize 提升至 128MB，timeout 25s
- 遊戲開始時在地圖上繪製藍色虛線邊界矩形（`L.rectangle`），讓玩家看到遊玩範圍
- 快取 key 升至 `bld3_*` 使舊的局部快取失效
- 修正 `fetchBuildingsDirect` 內 `const n` / `var n` 變數遮蔽 bug

**排行榜**：無 `setInterval`/`setTimeout`/`<meta refresh>`，純靜態渲染，不自動刷新。

---

### 2026-05-19 app.py 關鍵 bug 修復（最新）

**Nominatim 429 錯誤 → 遊戲永遠卡在 loading**
- 根本原因：Nominatim 免費 API 有嚴格速率限制；多次請求 Taipei 等熱門城市觸發 429
- 修正：新增 `_KNOWN_CITIES` dict，內含 28 個常用城市（台北/東京/首爾/香港/新加坡等）的精確座標
- 邏輯：`_bg_prepare` 先查 `_known_cities`，命中則完全跳過 Nominatim；未知城市才呼叫 Nominatim

**`make_response` 未 import → Cache-Control 無法生效**
- `/game` 路由使用 `make_response()` 添加 `Cache-Control: no-store` 頭，但 import 漏了 `make_response`
- 修正：在 Flask import 行加入 `make_response`

**Cache-Control 頭（防止瀏覽器快取舊 HTML）**
- `/game` 路由回應加入 `Cache-Control: no-store, no-cache, must-revalidate` 和 `Pragma: no-cache`
- 防止瀏覽器快取含舊「🔌 連線中…」文字的 game.html

---

### 2026-05-19 建築物載入修復（最新）

**根本原因修復：`catch{}` 語法錯誤導致整個 script 無法執行**
- `game.html` 中 `try{ return await Promise.any(...); }catch{ ... }` 的 `catch{}` 無參數屬於 ES2019 optional catch binding
- 在 Chrome <66 等舊版瀏覽器為**語法錯誤**，整個 `<script>` 區塊不執行 → loading overlay 永遠停在預設文字
- 修正：改用相容所有瀏覽器的 `new Promise` + `AbortController` 手動實作「第一個成功鏡像獲勝」

**同步修正**
- 移除 `Promise.any`（ES2020），改用手動並行 + 17s 硬逾時
- 查詢半徑由 0.002° 改回 0.0013°（縮小 40% 查詢面積）
- 伺服器備援 `fetch('/roads?...')` 加入 25s AbortController 逾時（原本無逾時，可能永遠等待）

### 2026-05-19 雲端部署 + 性能優化更新摘要

**雲端部署（Render.com + GitHub）**
- app.py 加入 `PORT = int(os.environ.get("PORT", 5000))`，Render 環境變數自動注入
- 啟動優先使用 waitress（8 threads production WSGI）；未安裝時 fallback 到 `threaded=True` Flask dev server
- `Procfile`：`web: python app.py`
- 永久公開網址：https://treasure-hunt-lew0.onrender.com
- 部署方式：`git add -A && git commit -m "..." && git push origin master` → Render 約 2-3 分鐘自動重部署
- 注意：Render 免費方案 15 分鐘無人使用後睡眠，首次訪問冷啟動 30-50s

**排行榜 GitHub API 持久化（game/models.py 重寫）**
- Render 磁碟為 ephemeral（重部署後清空），用 GitHub Contents API 持久化 `scores.json`
- `_gh_load()`：GET `repos/timmyweistudy-design/treasure-hunt/contents/scores.json`，回傳 (scores, sha) 或 None
- `_gh_save(scores, sha)`：PUT 同路徑，帶當前 SHA，寫回 GitHub repo
- `Scoreboard._load()`：優先 GitHub，失敗 fallback 本機檔案
- `Scoreboard.save_score()`：先寫 GitHub（更新 `self._sha`），再本機備份（失敗靜默）
- 需在 Render 環境變數設 `GITHUB_TOKEN = ghp_...`
- `.gitignore` 加入 `scores.json` 防止 git push 覆蓋 GitHub API 管理的檔案

**幀節流系統（frame throttling）**
- 新增 `frameCount`、`uiFrame`（每 4 幀=~15fps）、`aiFrame`（每 2 幀=~30fps）計數器
- `uiFrame`（15fps）：DOM 更新 — `updateMiniMap()`、`updateDistances()`、AI chip 文字、sprint bar/label、全部 `tickEffects` 的 display/textContent 操作
- `aiFrame`（30fps）：AI marker 位置同步（`ai.marker.setLatLng`）+ `map.setView`（在 `tryMove` 末尾 `if(aiFrame)` 才執行）
- `throttledViewUpdate()` 函式已移除，map.setView 移至 `tryMove` 內 `if(aiFrame)` 條件
- 效果：低階裝置不再因每幀 900+ DOM 操作卡頓，遠端玩家按鍵延遲/漂移/卡住大幅改善

**非同步 A*（requestIdleCallback）**
- tickChaser/tickPatroller/tickThief 的 A* 呼叫改為 `(requestIdleCallback||setTimeout)(()=>{...})`
- 新增 per-ai `_astarPending` flag，pending 期間不重複排程
- 修正：`dropDecoy()` 和 `tickDecoy()` 到期時同時重置 `ai.pathTimer=0` 和 `ai._astarPending=false`，否則 pending flag 卡住，A* 永不重算

**按鍵系統（key system）**
- 最終方案：`keys[e.key] = true`（布林值），`delete keys[e.key]` on keyup
- `clearAllKeys()`：清除所有 keys；在 `blur`、`visibilitychange`（隱藏）、`focus`（重新獲焦）三事件觸發
- 遊戲循環在每幀檢查 `if(!document.hasFocus()) clearAllKeys()`，確保失焦後不持續移動
- 移除先前的 MOVE_KEYS timestamp 方案（400ms/700ms timeout），該方案導致衝刺 Shift 鍵誤判

**對角線移動修正（tryMove）**
- 舊版：對角線被擋 → `else if` 只試 lat → 放棄；無法同時通過 lat+lon 獨立滑牆
- 新版：對角線被擋後，**獨立**嘗試 lat 和 lon（兩者都可各自成功）：
  ```javascript
  if(dLat&&!isInBuilding(pLat+dLat,pLon)){pLat+=dLat;moved=true;}
  if(dLon&&!isInBuilding(pLat,pLon+dLon)){pLon+=dLon;moved=true;}
  ```
- 修正同時按上+右遇牆只走單一方向的 bug

**道具 DOM 快取（tickItems）**
- `item._badgeEl` 快取道具 marker 的 `.item-badge` element，避免每幀重複查詢 DOM

### 2026-05-19 舊更新摘要

**移除無碰撞模式**
- 刪除「跳過（無碰撞模式）」按鈕與 `skipLoading()` 函式
- 載入失敗改為顯示「重試」按鈕；建築物資料不足時跳回首頁
- 載入動畫縮短（overview 2200→1400ms，zoom 900→700ms，pre-start 400→200ms）

**路線細格 A*（紅線不再穿建築）**
- 新增 `ROUTE_CELL = 0.0001°`（11m/格，比 AI nav grid 精細 4 倍）
- 新增 `buildRouteGrid()` / `runRouteAstar()` 專用函式（MAX_VIS=16000）
- `rebuildOptimalRouteAstar()` 改用此細格，AI 導航格保持原 44m（快）
- 路徑頂點全部保留（移除舊的每3格取1過濾，避免線段跨越窄建築物）

**磁鐵道具修正（game.html）**
- 新增 `MAGNET_R = CLCT_R * 8`（400m），磁鐵不再受限於普通 50m 收集半徑
- 磁鐵啟動時在地圖上顯示橙色虛線大圓（400m），移動時跟著玩家走，計時結束自動消失
- 自動收集間隔 0.4s→0.3s
- 磁鐵只吸道具（`applyItem`），不再自動收集寶藏

**巡邏守衛視野放大（game.html）**
- 巡邏守衛圓點維持原始 42px 不變
- `PATROLLER_FOV_LEN` 50m → 120m、`PATROLLER_FOV_HW` 8m → 20m（視野面積擴大約 6 倍）
- FOV 多邊形從三角形改為長方形（4 頂點：守衛兩側底邊 + 前方兩側遠端）
- `inPatrollerFOV()` 碰撞偵測自動使用新常數，範圍一致

**磁鐵吸引動畫（game.html）**
- 磁鐵啟動時，400m 內道具不再瞬間消失，改為動畫飛向玩家（0.55s）
- 飛行中道具會縮小（scale 1→0.3）並旋轉 360°，到達後自動 `applyItem`
- `pullingItems` Map 追蹤飛行中道具；`tickPullingItems(dt)` 每幀更新位置
- `.item-badge.pulling` CSS：持續金色光暈脈衝

**分數浮動文字（game.html）**
- 每次收集寶藏，從寶藏地圖座標浮出 `+N` 金色文字，0.9s 後消失
- CSS `@keyframes float-up`：Y-65px + scale 1.3 + fade out
- `showScoreFloat(lat, lon, gained)` 使用 `map.latLngToContainerPoint` 定位

**路線即時更新（game.html）**
- 每次收集寶藏後呼叫 `rebuildOptimalRouteAstar()`，路線從玩家目前位置出發、略過已收集
- 全部收集完畢時自動移除路線圖層
- `routeGrid` 改為全域快取（建築物載入後建一次），不再每次重建

**自適應路線格子大小（game.html）**
- `ROUTE_CELL` 不再固定 0.0001，改為 `max(0.0001, max(bbox_h, bbox_w) / 180)`
- 小城市維持 11m 精度；大城市自動放大格子，確保格子數 ≤ 180×180 避免凍結

**飄移 + 卡牆修正（game.html）**
- **飄移根本原因**：cloudflare tunnel 偶爾讓瀏覽器短暫失焦，`keyup` 事件不觸發 → key 永遠留在 `keys` → 角色持續往同方向移動
- 新增 `clearAllKeys()` 函式；在 `blur`、`visibilitychange`（頁面隱藏）、`focus`（重新獲焦）三個事件都清除所有按鍵狀態
- **卡牆根本原因**：兩個方向鍵同時卡住（如 W+D 卡住），對角方向、lat 方向、lon 方向全部撞牆 → 完全無法移動
- `tryMove` 的完全阻擋 else 分支：`blockFlash > 60`（約 1 秒）時自動呼叫 `ensureOutsideBuilding()` 傳送到最近可走格子 + 呼叫 `clearAllKeys()` 清除卡住的按鍵

**多人操控凍結修正（game.html + app.py）**
- **根本原因**：`loop()` 的 `requestAnimationFrame(loop)` 在 `if(gameReady)` 區塊外，但若 tick 函式拋出例外，例外會往上傳播跳過 RAF 呼叫，遊戲迴圈永久停止（timer 用 setInterval 獨立跑所以還在動）
- **修正**：`if(gameReady)` 內的全部 tick 邏輯包進 `try/catch`，任何例外只 `console.error` 記錄，`requestAnimationFrame(loop)` 永遠執行
- **路線重算延遲**：`rebuildOptimalRouteAstar()` 改為 `setTimeout(..., 50)` 在收集後 50ms 才執行，避免 A* 計算阻塞主線程造成短暫卡頓
- **Flask 換 waitress 伺服器**（app.py）：`pip install waitress` 後自動使用 8 threads 的 production WSGI；若未安裝則 fallback 到 `threaded=True` 的 Werkzeug dev server
- 重啟 Flask 後新設定生效：先在 Windows 終端機按 Ctrl+C 停止，再執行 `venv\Scripts\python app.py`

**道具生成距離修正 + 建築物迴避（game.html）**
- 近寶藏生成的道具距離：40-100m → **150-300m**，確保需要範圍道具才能從寶藏處拿到
- 隨機及近寶藏兩種生成方式均加入 **建築物重試**（最多 8 次），避免道具生成在無法進入的建築內

**道具即將消失警告（game.html）**
- `tickItems` 在 `timer < 10s` 時為 `.item-badge` 加上 `.warn` class
- `.warn` CSS：scale 脈衝動畫 + 紅色外框光暈，提醒玩家趕快去撿
- `timer < 5s` 時仍保留原有透明度漸淡效果

**連擊倒數視覺條（game.html）**
- 連擊 chip 使用 `backgroundImage: linear-gradient` 顯示剩餘時間進度
- 從左到右以金色填滿，右側透明，每幀即時更新，比單純秒數更直覺

**節流視圖更新修正遠端玩家延遲（game.html）**
- **根本原因**：`tryMove` 每幀（~60fps）都呼叫 `map.setView`、`updateMiniMap()`、`updateDistances()`，合計 900+ DOM 操作/秒，低階裝置幀率崩潰導致按鍵延遲、飄移、卡住
- **修正**：從 `tryMove` 移除三個昂貴呼叫；新增 `throttledViewUpdate(ts)` 函式，只在距上次更新 ≥67ms（~15fps）才執行 `map.setView + updateMiniMap + updateDistances`
- `tryMove` 只保留 `pMarker.setLatLng` / `pCircle.setLatLng`（純資料更新，幾乎無 DOM 開銷）
- `throttledViewUpdate(ts)` 在 `loop()` 的 `gameReady` 區塊最末呼叫（try/catch 保護內）

**修正遊戲當機 bug（game.html）**
- `spawnItem()` 的近寶藏偏移計算誤用 `DLat`（只在 `updateFOVPoly` 函式內定義的區域變數）
- 全域取不到 `DLat` → `rd = NaN` → `lat = NaN, lon = NaN` → Leaflet 嘗試渲染座標 NaN 的 marker 導致當機
- 修正：改為字面值 `1/111111`（≈11m/°，正確公尺→度換算）

**範圍道具生成偏向寶藏附近（game.html）**
- `spawnItem()` 改寫：50% 機率選一個未收集寶藏附近（40~100m）生成道具
- 近寶藏時：`range` 機率 60%，其他各 10%（原本全平均 20%）
- 遠離寶藏時（隨機位置）：維持原機率分布

**最佳路線 waypoint 吸附修正（game.html）**
- 新增 `snapToUnblocked(rg, lat, lon)`：BFS 找最近未被建築物阻擋的格子
- `rebuildOptimalRouteAstar()` 現在先對每個 waypoint（起點、各寶藏）做吸附，再跑 A*
- 根本原因：寶藏 POI（咖啡廳/博物館等）座標位於建築物多邊形內，A* 目標格被標記為 blocked，無法抵達 → 只有剛好落在道路格的線段能找到路

**建築物排除規則修正（map_api.py）**
- 新增 `building="roof"` 排除（純屋頂投影，底下可通行）
- 新增 `layer < 0` 排除（地下建築如地下道，地面層可通行）
- 橋梁、高架橋、高速公路、地下道、巷弄本為 `highway=*` 標籤，從不進入 buildings 陣列，始終可通行（此為原本正確行為，本次確認無誤）

**載入加速**
- `app.py` 在 `/start` 回傳 HTML 前，用 `threading.Thread` 背景預取 `fetch_roads_bbox`
- 下次瀏覽器請求 `/roads` 時直接從 `_road_cache` 回傳，等待時間大幅縮短

**UI 整理**
- 鍵盤操作說明改成可折疊（預設收合，點擊展開）
- 羅盤和寶藏清單移到說明上方，讓重要資訊不被遮蓋

### UI 美化摘要（UI Orbitron 字型，同日）
- **index.html**：深色星空主題、Orbitron 標題、glassmorphism 卡片、分數數字 Orbitron、排行榜前三名色彩區分
- **finish.html**：深色結算頁、分數從 0 滾動到最終值動畫（JS requestAnimationFrame）、每格統計卡各自漸層色
- **game.html**：
  - Header 改為深色（#0d1117）、分數/計時器換 Orbitron 字型並加色彩（分數金、計時藍）
  - 玩家 marker：34px → 44px，放射漸層藍、 🏃 emoji、脈動光暈加強
  - AI 追跡者：36px → 42px，放射漸層紅
  - 巡邏守衛：36px → 42px，放射漸層紫
  - 寶物小偷：36px → 42px，放射漸層深灰
  - 寶藏 badge：28px → 34px，陰影加強
  - 倒數數字（3-2-1 GO）換 Orbitron + 漸層色
  - Toast 改毛玻璃效果（backdrop-filter blur）
  - 小地圖 hover 放大效果

### 遊戲流程
```
首頁輸入名字+城市
  → POST /start
    → Nominatim geocode 城市座標
    → Overpass 抓 5 個 POI（cafe/museum/park/library/restaurant）
    → solve_tsp_exact 計算最短順序
    → OSRM 取得步行路線座標
    → 計算 bounding box（起點 + 所有寶藏 + 220m margin）
    → render game.html（含所有 JSON 資料）
  → 瀏覽器載入 game.html
    → 非同步 GET /roads?s=&n=&w=&e= 取得建築物多邊形
    → 載入完成 → 地圖概覽動畫 → 3-2-1 倒數 → 開始
  → 玩家 WASD 移動，Space/按鈕收集寶藏
    → POST /collect/<id>（含 order_bonus）
  → 時間到 or 全收集 → GET /finish → 計算時間獎勵 → 存排行榜
```

---

## 2. 資料夾結構

```
timmy-agent/
├── app.py                  # Flask 主程式，所有路由
├── config.py               # 全域常數（API URL、遊戲設定）
├── CODEBASE.md             # ← 本文件（每次更新都同步）
├── .vscode/
│   └── settings.json       # VS Code 設定
├── data/
│   └── scores.json         # 排行榜（自動生成）
├── game/
│   ├── __init__.py
│   ├── map_api.py          # 所有外部 API 呼叫 + 記憶體快取
│   ├── models.py           # Treasure / Player / Scoreboard dataclass
│   └── pathfinder.py       # TSP 演算法 + Haversine
├── static/
│   ├── leaflet.css         # Leaflet 地圖 CSS（本地離線版）
│   ├── leaflet.js          # Leaflet 地圖 JS 函式庫（本地離線版）
│   ├── marker-icon.png     # Leaflet 預設 marker 圖示
│   └── marker-shadow.png   # Leaflet marker 陰影
├── templates/
│   ├── index.html          # 首頁（輸入表單 + 排行榜）
│   ├── game.html           # 遊戲主畫面（Leaflet + 所有遊戲邏輯）
│   └── finish.html         # 結算畫面
└── venv/                   # Python 虛擬環境
```

---

## 3. 啟動方式

### 本機開發（WSL2）
```bash
cd /mnt/c/Users/timmy/Downloads/timmy-agent

# 安裝依賴（僅首次）
venv/bin/pip install flask requests waitress

# 啟動伺服器
venv/bin/python app.py
# → Starting with waitress on port 5000...

# 在 Windows 瀏覽器開啟（WSL2 IP）
# http://172.18.227.118:5000
```

### 雲端部署（Render.com）

永久公開網址：**https://treasure-hunt-lew0.onrender.com**

部署步驟：
```bash
git add -A
git commit -m "描述"
git push origin master
# Render 自動偵測 push → 重新部署（約 2-3 分鐘）
```

注意事項：
- Render 免費方案：15 分鐘無人使用後睡眠，首次訪問冷啟動 30-50s
- Render 環境變數需設 `GITHUB_TOKEN`（排行榜持久化用）
- Render 磁碟 ephemeral（每次部署重置），排行榜靠 GitHub API 持久化
- 如果 `git push` 失敗（因 GitHub API 寫入 scores.json 導致落後），先 `git pull --rebase origin master` 再 push

---

## 4. 遊戲設定

```python
# config.py
GAME_CONFIG = {
    "time_limit":       600,   # 遊戲時間（秒）= 10 分鐘
    "treasure_count":   5,     # 寶藏數量
    "search_radius":    2000,  # POI 搜尋半徑（公尺，參考用）
    "collect_radius":   50,    # 收集範圍（公尺），WASD 走到附近才能收集
    "time_bonus_rate":  1,     # 每剩 1 秒加幾分（最多 600×1=600）
    "categories": ["cafe", "museum", "park", "library", "restaurant"]
}
```

---

## 5. 計分公式

```
總分 = 寶藏分 + 順序獎勵 + 連擊獎勵 + 黃金獎勵 + 時間獎勵 - AI扣分

寶藏分     = 依離起點距離計算：max(50, min(500, round((50 + dist_m*0.3)/10)*10))
             （越遠分越高，最低50最高500）
順序獎勵   = 按 TSP 最優順序收集每個 +50 分（最多 5×50 = 250）
連擊獎勵   = 22秒內連續收集：第2寶×30、第3寶×60、第4寶×90…（(n-1)×30）
黃金獎勵   = 黃金寶藏生效期間收集：額外 +寶藏原分×(3-1) = 原分×2
時間獎勵   = (600 - 實際用時秒數) × 1（最多 600 分）
AI扣分     = 被追跡者觸碰 -50 分（8秒冷卻）
```

---

## 6. 後端路由總覽

| 方法 | 路由 | 說明 |
|------|------|------|
| GET  | `/` | 首頁，顯示表單 + 排行榜 |
| POST | `/start` | 開始遊戲，geocode → POI → TSP → 渲染 game.html |
| GET  | `/roads` | 取得建築物多邊形（優先用 bbox 參數 s/n/w/e，有快取） |
| POST | `/collect/<id>` | 收集寶藏，JSON body `{"order_bonus": N}`（順序獎勵 + 連擊獎勵合併） |
| POST | `/penalty` | AI 攻擊扣分，JSON body `{"amount": 50}`，同步 session 分數 |
| GET  | `/finish` | 結算，計算時間獎勵，存排行榜 |

---

## 7. 完整程式碼

---

### config.py

```python
NOMINATIM_URL = "https://nominatim.openstreetmap.org"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OSRM_URL = "https://router.project-osrm.org"

GAME_CONFIG = {
    "time_limit": 600,          # 10 分鐘
    "treasure_count": 5,
    "search_radius": 2000,
    "collect_radius": 50,           # 收集範圍（公尺），WASD 走到附近才能收集
    "time_bonus_rate": 1,           # 每剩1秒加幾分（最多 600*1=600 加分）
    "categories": ["cafe", "museum", "park", "library", "restaurant"]
}
```

---

### app.py

```python
import os
import json
import time
from flask import Flask, render_template, request, session, jsonify, redirect, url_for
from game.models import Player, Scoreboard
from game.map_api import MapAPI
from game.pathfinder import solve_tsp_exact, calculate_total_distance
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


@app.route("/finish")
def finish_game():
    player_data = session.get("player", {})
    treasures_data = session.get("treasures", [])

    if not player_data:
        return redirect(url_for("index"))

    player = Player(
        name=player_data.get("name", "玩家"),
        lat=player_data.get("lat", 0),
        lon=player_data.get("lon", 0),
        score=player_data.get("score", 0),
        found_treasures=player_data.get("found_treasures", []),
        start_time=player_data.get("start_time", time.time())
    )

    # 時間獎勵：每剩 1 秒 +1 分（最多 600 分）
    elapsed = min(player.elapsed_time, GAME_CONFIG["time_limit"])
    time_bonus = max(0, int((GAME_CONFIG["time_limit"] - elapsed) * GAME_CONFIG["time_bonus_rate"]))
    player.score += time_bonus

    city = player_data.get("city", "")
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
```

---

### game/models.py

```python
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


import base64, os

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
```

---

### game/pathfinder.py

```python
import math
from itertools import permutations
from typing import List, Tuple


def haversine(coord1: Tuple, coord2: Tuple) -> float:
    R = 6371000
    lat1, lon1 = math.radians(coord1[0]), math.radians(coord1[1])
    lat2, lon2 = math.radians(coord2[0]), math.radians(coord2[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))


def solve_tsp_nearest_neighbor(start: Tuple, treasures: List) -> List:
    if not treasures:
        return []
    unvisited = list(range(len(treasures)))
    route = []
    current = start
    while unvisited:
        nearest_idx = min(unvisited, key=lambda i: haversine(current, treasures[i].coords))
        route.append(treasures[nearest_idx])
        current = treasures[nearest_idx].coords
        unvisited.remove(nearest_idx)
    return route


def solve_tsp_exact(start: Tuple, treasures: List) -> List:
    if len(treasures) > 8:
        return solve_tsp_nearest_neighbor(start, treasures)
    if not treasures:
        return []
    best_route, best_dist = None, float("inf")
    for perm in permutations(range(len(treasures))):
        dist = haversine(start, treasures[perm[0]].coords)
        for i in range(len(perm) - 1):
            dist += haversine(treasures[perm[i]].coords, treasures[perm[i+1]].coords)
        if dist < best_dist:
            best_dist = dist
            best_route = [treasures[i] for i in perm]
    return best_route or []


def calculate_total_distance(start: Tuple, route: List) -> float:
    if not route:
        return 0
    coords = [start] + [t.coords for t in route]
    return sum(haversine(coords[i], coords[i+1]) for i in range(len(coords)-1))
```

---

### game/map_api.py

```python
import requests
import random
from config import NOMINATIM_URL, OSRM_URL, GAME_CONFIG
from game.models import Treasure, rate_limit

OVERPASS_MIRRORS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]

HEADERS = {"User-Agent": "TreasureHuntGame/1.0", "Accept": "*/*"}


class MapAPI:
    _road_cache: dict = {}   # (round_lat2, round_lon2) → parsed data

    @staticmethod
    @rate_limit(calls_per_second=1)
    def geocode(city_name: str) -> dict:
        params = {"q": city_name, "format": "json", "limit": 1}
        resp = requests.get(f"{NOMINATIM_URL}/search", params=params, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        results = resp.json()
        if not results:
            raise ValueError(f"找不到城市: {city_name}")
        return {"lat": float(results[0]["lat"]), "lon": float(results[0]["lon"])}

    @staticmethod
    def _query_overpass(query: str) -> list:
        last_err = None
        for url in OVERPASS_MIRRORS:
            try:
                resp = requests.post(url, data={"data": query}, headers=HEADERS, timeout=8)
                resp.raise_for_status()
                return resp.json().get("elements", [])
            except Exception as e:
                last_err = e
        raise last_err

    @staticmethod
    def fetch_roads(lat: float, lon: float) -> dict:
        """後備方法：以起點為中心固定 900m 半徑查詢建築物。"""
        key = (round(lat, 2), round(lon, 2))
        if key in MapAPI._road_cache:
            return MapAPI._road_cache[key]

        d = 0.008
        query = (
            f"[out:json][timeout:10];"
            f"(way[\"highway\"~\"^(primary|secondary|tertiary|residential|service|"
            f"footway|pedestrian|path|living_street|unclassified|steps)$\"]"
            f"({lat-d},{lon-d},{lat+d},{lon+d});"
            f"way[\"building\"]({lat-d},{lon-d},{lat+d},{lon+d}););"
            f"(._;>;);out body;"
        )
        for url in OVERPASS_MIRRORS:
            try:
                resp = requests.post(url, data={"data": query}, headers=HEADERS, timeout=10)
                resp.raise_for_status()
                result = MapAPI._parse_map_data(resp.json())
                MapAPI._road_cache[key] = result
                return result
            except Exception:
                continue
        return {"roads": {"type": "FeatureCollection", "features": []}, "buildings": []}

    @staticmethod
    def fetch_roads_bbox(s: float, n: float, w: float, e: float) -> dict:
        """主要方法：查詢建築物多邊形，覆蓋起點到所有寶藏的完整 bounding box，有記憶體快取。"""
        key = (round(s, 3), round(n, 3), round(w, 3), round(e, 3))
        if key in MapAPI._road_cache:
            return MapAPI._road_cache[key]

        query = (
            f"[out:json][timeout:25][maxsize:67108864];"
            f"way[\"building\"]({s},{w},{n},{e});"
            f"(._;>;);out body;"
        )
        for url in OVERPASS_MIRRORS:
            try:
                resp = requests.post(url, data={"data": query}, headers=HEADERS, timeout=28)
                resp.raise_for_status()
                result = MapAPI._parse_map_data(resp.json())
                MapAPI._road_cache[key] = result
                return result
            except Exception:
                continue

        # 全 bbox 失敗時，改抓城市中心附近的小範圍作為備援
        clat, clon = (s + n) / 2, (w + e) / 2
        fallback = MapAPI.fetch_roads(clat, clon)
        if fallback["buildings"]:
            MapAPI._road_cache[key] = fallback
        return fallback

    @staticmethod
    def _parse_map_data(data: dict) -> dict:
        nodes = {e["id"]: [e["lon"], e["lat"]] for e in data.get("elements", []) if e["type"] == "node"}
        road_features, buildings = [], []
        for e in data.get("elements", []):
            if e["type"] != "way":
                continue
            tags = e.get("tags", {})
            coords = [nodes[n] for n in e.get("nodes", []) if n in nodes]
            if "highway" in tags and len(coords) >= 2:
                road_features.append({
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": coords},
                    "properties": {"hw": tags.get("highway", "")}
                })
            elif "building" in tags and len(coords) >= 4:
                # 橋梁 / 隧道結構排除，避免阻擋玩家通行
                if tags.get("bridge") or tags.get("man_made") == "bridge" or tags.get("tunnel"):
                    continue
                # 超過 24 頂點的多邊形抽稀至 20 點
                if len(coords) > 24:
                    step = max(1, len(coords) // 20)
                    coords = coords[::step]
                buildings.append(coords)
        return {
            "roads": {"type": "FeatureCollection", "features": road_features},
            "buildings": buildings[:3500]
        }

    @staticmethod
    def fetch_poi(lat: float, lon: float) -> list:
        d = 0.010
        queries = [
            f'[out:json][timeout:8];(node["amenity"="cafe"]({lat-d},{lon-d},{lat+d},{lon+d});node["tourism"="museum"]({lat-d},{lon-d},{lat+d},{lon+d});node["amenity"="library"]({lat-d},{lon-d},{lat+d},{lon+d}););out body;',
            f'[out:json][timeout:8];(node["leisure"="park"]({lat-d},{lon-d},{lat+d},{lon+d});node["amenity"="restaurant"]({lat-d},{lon-d},{lat+d},{lon+d}););out body;',
        ]
        elements = []
        for q in queries:
            try:
                elements += MapAPI._query_overpass(q)
                if len(elements) >= GAME_CONFIG["treasure_count"] * 4:
                    break
            except Exception:
                pass

        if not elements:
            return MapAPI._fetch_poi_nominatim(lat, lon)

        valid = [e for e in elements if "name" in e.get("tags", {})]
        count = min(GAME_CONFIG["treasure_count"], len(valid))
        if count == 0:
            return MapAPI._fetch_poi_nominatim(lat, lon)

        selected = random.sample(valid, count)
        treasures = []
        for i, poi in enumerate(selected):
            tags = poi.get("tags", {})
            category = tags.get("amenity") or tags.get("tourism") or tags.get("leisure", "place")
            treasures.append(Treasure(
                id=f"t{i}",
                name=tags.get("name", f"神秘地點 {i+1}"),
                lat=poi["lat"],
                lon=poi["lon"],
                category=category,
                points=100
            ))
        return treasures

    @staticmethod
    @rate_limit(calls_per_second=1)
    def _fetch_poi_nominatim(lat: float, lon: float) -> list:
        keywords = ["cafe", "museum", "park", "restaurant", "library", "temple", "hotel"]
        results = []
        for kw in keywords:
            if len(results) >= GAME_CONFIG["treasure_count"]:
                break
            try:
                params = {
                    "q": kw, "format": "json", "limit": 3,
                    "viewbox": f"{lon-0.05},{lat+0.05},{lon+0.05},{lat-0.05}",
                    "bounded": 1
                }
                resp = requests.get(f"{NOMINATIM_URL}/search", params=params, headers=HEADERS, timeout=8)
                for r in resp.json():
                    if r.get("display_name") and len(results) < GAME_CONFIG["treasure_count"]:
                        results.append(r)
            except Exception:
                continue

        if not results:
            raise ValueError("無法取得周邊地點，請換一個城市試試")

        treasures = []
        for i, r in enumerate(results[:GAME_CONFIG["treasure_count"]]):
            name = r.get("name") or r["display_name"].split(",")[0]
            category = r.get("type", "place")
            treasures.append(Treasure(
                id=f"t{i}", name=name,
                lat=float(r["lat"]), lon=float(r["lon"]),
                category=category, points=100
            ))
        return treasures

    @staticmethod
    def get_route(coords: list) -> list:
        coord_str = ";".join(f"{lon},{lat}" for lat, lon in coords)
        url = f"{OSRM_URL}/route/v1/walking/{coord_str}"
        params = {"overview": "full", "geometries": "geojson"}
        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            return resp.json()["routes"][0]["geometry"]["coordinates"]
        except Exception:
            return []
```

---

### templates/index.html

```html
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <title>🗺️ 地圖尋寶大冒險</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: Arial, sans-serif; background: #f0f4f8; min-height: 100vh; }
        .hero { text-align: center; background: linear-gradient(135deg, #1a73e8, #34a853);
                color: white; padding: 50px 20px; }
        .hero h1 { font-size: 2.5rem; margin-bottom: 10px; }
        .hero p { font-size: 1.1rem; opacity: 0.9; }
        .container { max-width: 700px; margin: 40px auto; padding: 0 20px; }
        .card { background: white; border-radius: 12px; padding: 30px;
                box-shadow: 0 2px 12px rgba(0,0,0,0.1); margin-bottom: 30px; }
        .card h2 { margin-bottom: 20px; color: #333; }
        .form-row { display: flex; gap: 12px; flex-wrap: wrap; }
        input[type="text"] { flex: 1; padding: 12px 16px; font-size: 15px;
                              border: 2px solid #ddd; border-radius: 8px; outline: none; }
        input[type="text"]:focus { border-color: #1a73e8; }
        button[type="submit"] { padding: 12px 28px; font-size: 15px; font-weight: bold;
                                 background: #1a73e8; color: white; border: none;
                                 border-radius: 8px; cursor: pointer; }
        button[type="submit"]:hover { background: #1558b0; }
        .error { background: #fce8e6; color: #c62828; padding: 12px 16px;
                 border-radius: 8px; margin-bottom: 20px; }
        table { width: 100%; border-collapse: collapse; }
        th { background: #f5f5f5; padding: 10px; text-align: left; font-size: 14px; color: #555; }
        td { padding: 10px; border-bottom: 1px solid #eee; font-size: 14px; }
        tr:first-child td { font-weight: bold; color: #e8a000; }
        .badge { display: inline-block; background: #1a73e8; color: white;
                 padding: 2px 8px; border-radius: 12px; font-size: 12px; }
    </style>
</head>
<body>
    <div class="hero">
        <h1>🗺️ 地圖尋寶大冒險</h1>
        <p>在真實城市中尋找寶藏，規劃最短路線，挑戰排行榜！</p>
    </div>
    <div class="container">
        {% if error %}<div class="error">⚠️ {{ error }}</div>{% endif %}
        <div class="card">
            <h2>🚀 開始遊戲</h2>
            <form action="/start" method="POST">
                <div class="form-row">
                    <input type="text" name="player_name" placeholder="你的名字" required maxlength="20">
                    <input type="text" name="city" placeholder="城市（Taipei、Tokyo、Paris...）" value="Taipei" required>
                    <button type="submit">開始尋寶！</button>
                </div>
            </form>
        </div>
        <div class="card">
            <h2>📖 遊戲說明</h2>
            <ul style="padding-left:20px;line-height:2">
                <li>系統會在城市地圖上隨機放置 <b>5 個寶藏</b></li>
                <li>AI 會幫你計算 <b>最短尋寶路線（TSP 演算法）</b></li>
                <li>限時 <b>10 分鐘</b>，找到越多分數越高</li>
                <li>所有地點都是 <b>真實存在</b> 的咖啡廳、博物館、公園等</li>
            </ul>
        </div>
        {% if top10 %}
        <div class="card">
            <h2>🏆 全球排行榜</h2>
            <table>
                <tr><th>名次</th><th>玩家</th><th>城市</th><th>分數</th><th>寶藏</th><th>時間</th></tr>
                {% for s in top10 %}
                <tr>
                    <td>{% if loop.index==1 %}🥇{% elif loop.index==2 %}🥈{% elif loop.index==3 %}🥉{% else %}{{ loop.index }}{% endif %}</td>
                    <td>{{ s.name }}</td>
                    <td><span class="badge">{{ s.city or '?' }}</span></td>
                    <td><b>{{ s.score }}</b></td>
                    <td>{{ s.treasures }} 個</td><td>{{ s.time }}s</td>
                </tr>
                {% endfor %}
            </table>
        </div>
        {% endif %}
    </div>
</body>
</html>
```

---

### templates/game.html

> **重要**：此檔案約 1100 行，包含所有遊戲邏輯。以下列出關鍵常數與函式索引，完整內容請直接閱讀 `templates/game.html`。

**JS 常數（從 Flask 注入）**

| 常數 | 型別 | 說明 |
|------|------|------|
| `TREASURES` | Array | 所有寶藏資料 `[{id,name,lat,lon,category,points,found}]` |
| `OPTIMAL` | Array | TSP 最優順序 id 陣列 `["t2","t0","t4",...]` |
| `ROUTE_COORDS` | Array | OSRM 路線座標 `[[lon,lat],...]` |
| `START` | `[lat,lon]` | 玩家起始座標 |
| `TIME_LIMIT` | number | 600（秒） |
| `CLCT_R` | number | 50（公尺，收集範圍） |
| `BOUNDS` | Object | `{s,n,w,e}` 建築物查詢 bbox |
| `WALK_SPD` | number | 0.00025 度/秒 ≈ 28 m/s |
| `SPRINT_SPD` | number | 0.00050 度/秒 ≈ 55 m/s |
| `SPRINT_MAX` | number | 10（衝刺最大秒數） |
| `COOL_T` | number | 3（冷卻秒數） |
| `ORDER_BONUS` | number | 50（順序加分） |
| `AI_SPD` | number | 0.00020 度/秒 ≈ 22 m/s（略慢於玩家步行） |
| `AI_ATTACK_R` | number | 25（公尺，觸發攻擊距離） |
| `AI_ATTACK_CD` | number | 8（秒，攻擊冷卻） |
| `AI_SPAWN_DELAY` | number | 25（秒，遊戲開始後第一隻出現） |
| `AI_WAVE_INTERVAL` | number | 60（秒，之後每隔多久追加一隻） |
| `AI_MAX` | number | 16（10巡邏守衛 + 3追跡者 + 3小偷） |
| `THIEF_DELAY` | number | 100（第一隻小偷出現倒數秒數） |
| `THIEF_WAVE_INTERVAL` | number | 100（小偷追加間隔秒數） |
| `THIEF_MAX` | number | 3（小偷最多隻數） |
| `ITEM_IVTL` | number | 4（秒，道具重生間隔） |
| `ITEM_LIFE` | number | 40（秒，道具存在時間） |
| `ITEM_MAX` | number | 10（地圖最多道具數） |
| `NAV_CELL` | number | 0.0004 度/格 ≈ 44m（A* 導航格尺寸） |
| `STUN_DURATION` | number | 3（定身持續秒數，玩家被凍住） |
| `STUN_CD` | number | 30（定身冷卻秒數，所有 AI 共用） |
| `STUN_R` | number | 65（AI 施放定身的觸發距離，公尺） |
| `GOLDEN_DURATION` | number | 15（黃金寶藏持續秒數） |
| `GOLDEN_INTERVAL` | number | 45（黃金寶藏出現間隔秒數） |
| `GOLDEN_MULT` | number | 3（黃金寶藏分數倍率） |
| `PATROLLER_FOV_LEN` | number | 50（巡邏守衛視野長度，公尺） |
| `PATROLLER_FOV_HW` | number | 8（巡邏守衛視野半寬，公尺） |
| `THIEF_STEAL_R` | number | 20（小偷偷竊觸發距離，公尺） |

**主要函式**

| 函式 | 說明 |
|------|------|
| `init()` | 非同步載入建築物 → 地圖概覽 → 呼叫 `startCountdown()` |
| `startCountdown()` | 3-2-1 動畫，結束後設 `gameReady=true`，啟動計時器 |
| `loop(ts)` | requestAnimationFrame 主迴圈：frameCount/uiFrame/aiFrame 節流 + WASD 移動；全包 try/catch 防止迴圈死亡 |
| `clearAllKeys()` | 清除所有 keys（blur/visibilitychange/focus 觸發，每幀 !hasFocus 也呼叫） |
| `tryMove(dLon,dLat)` | 移動 + Ray Casting 建築物碰撞 + 獨立軸滑牆（lat和lon分別嘗試）；`if(aiFrame) map.setView` |
| `tickSprint(dt)` | 衝刺狀態機：消耗/冷卻/被動回充(0.4/s)/UI 更新 |
| `updateDistances()` | 更新羅盤、各寶藏距離、接近虛線環、地圖 badge 狀態 |
| `collect(id,lat,lon)` | POST /collect → 播音效、噴粒子、更新 UI、連鎖提示 |
| `collectNearest()` | Space 鍵：找最近範圍內寶藏並呼叫 collect() |
| `spawnParticles(lat,lon)` | 在地圖座標噴出 12 顆彩色粒子（CSS animation） |
| `playCollect/Sprint/Blocked/Alarm/Win()` | Web Audio API 合成音效 |
| `toggleMute()` | 🔊/🔇 切換 |
| `updateMiniMap()` | 同步小地圖玩家位置 |
| `pushTrail(dt)` | 每 0.1s 記錄軌跡點（最多 60 點） |
| `loadBuildings(raw)` | 建立建築物碰撞結構（含 bounding box 預篩）+ 建立空間格 buildingGrid + 呼叫 buildNavGrid |
| `isInBuilding(lat,lon)` | 查空間格 → bounding box → Ray Casting 多邊形內點判斷 |
| `ensureOutsideBuilding()` | 若玩家在建築內則推出（8方向×4步距逐步嘗試），無敵結束時自動呼叫 |
| `dropDecoy()` | Q鍵：在玩家位置放置誘餌，所有 AI 轉追誘餌 6 秒；40 秒冷卻 |
| `tickDecoy(dt)` | 誘餌倒數 + 冷卻計時；到期時清除 marker 並強制 AI 立即重算路徑 |
| *(AI 定身邏輯)* | 在 tickAI 中：AI 距玩家 ≤65m 且 `stunCD===0` 時觸發；`stunTimer=3, stunCD=30`；所有 AI 共用 CD |
| `setGoldenTreasure(id)` | 讓指定寶藏變金色（tbadge.golden）+ 地圖金圈；toast 通知；收集可得 GOLDEN_MULT×分數 |
| `clearGoldenTreasure(expired)` | 清除黃金狀態、還原 marker、移除金圈；expired=true 時顯示「消失」toast |
| `tickGolden(dt)` | 每 45s 隨機一個未收集寶藏變黃金；倒數 15s 後自動清除 |
| `buildNavGrid()` | 在 BOUNDS 範圍內建立 Uint8Array 導航格（0=可走、1=建築），供 A* 使用 |
| `llToRC(lat,lon)` | 經緯度 → navGrid 格座標 (row, col) |
| `rcToLL(r,c)` | navGrid 格座標 → 經緯度中心 |
| `nearestWalkable(lat,lon)` | BFS 搜索最近的可走格，供 AI spawn 時避開建築物 |
| `runAstar(fLat,fLon,tLat,tLon)` | A* 路徑規劃，回傳 `[[lat,lon],...]` 路徑點（max 3000 節點）|
| `applyScorePenalty(amount,msg)` | DRY 扣分輔助：更新 score、動畫、toast、POST /penalty |
| `rebuildOptimalRouteAstar()` | 建築物載入後用 A* 重算最佳路徑，替換 OSRM 折線；確保路線繞過建築物 |
| `spawnAI(forceType,silent)` | 生成指定型別 AI；patroller 均勻分散起始路標（`pIdx*OPTIMAL.length/10`）；silent=true 不顯示 toast |
| `_updateThiefMarker(ai)` | 更新單隻小偷的目標標示 marker（ai.targetMarker），支援多隻小偷各自標示 |
| `tickChaser(ai,dt,s)` | 追跡者行為：A* 追玩家/誘餌、定身、攻擊、無敵期逃跑 |
| `tickPatroller(ai,dt,s)` | 巡邏守衛：沿 OPTIMAL 路標巡邏、FOV 偵測玩家（alertTimer/alertCD）|
| `tickThief(ai,dt,s)` | 寶物小偷：A* 追隨機寶藏、抵達後呼叫 `relocateTreasure`、速度×1.0（等同 AI_SPD） |
| `tickAI(dt)` | 統籌 AI 波次（3 種 + 小偷多波次）、dispatch 到 tickChaser/tickPatroller/tickThief |
| `inPatrollerFOV(ai)` | 計算玩家是否在巡邏守衛的 FOV 錐形內（點積+叉積投影） |
| `updateFOVPoly(ai)` | 更新/建立巡邏守衛的 L.polygon 視野三角形（apex→left_tip→right_tip）|
| `relocateTreasure(tId)` | 移動寶藏到隨機可走位置：更新 TREASURES 物件、marker、popup、minimap |
| `showToast(msg,ms)` | 顯示頂部通知 |
| `distM(la1,lo1,la2,lo2)` | Haversine 距離（公尺） |
| `bearingDeg(la1,lo1,la2,lo2)` | 方位角（度），用於羅盤箭頭旋轉 |

**遊戲功能清單**

- WASD / 方向鍵移動，Shift 衝刺，Space 收集 / 撿道具，**Q 誘餌信號彈**
- 建築物 Ray Casting 碰撞偵測 + 空間格加速 + 滑牆（對角線變軸向）
- Sprint：10s 持續 / 3s 冷卻全滿 / 步行 0.4/s 被動回充
- TSP 最優路線（紅色虛線）+ 羅盤指向下一目標
- 按最優順序收集 +50 分，連鎖 3+ 個顯示 🔥
- 收集範圍 50m，玩家位置圓 + 虛線接近環（2×）
- 小地圖（左下角）：顯示所有寶藏 + 路線，收集後灰化
- 移動軌跡（藍色虛線，60 個點）
- 分數跳動動畫、衝刺橙色光暈、危險紅色光暈（<60s）
- Web Audio 音效：收集 ding、衝刺 whoosh、撞牆 thud、60s 警報、勝利、道具撿取、AI攻擊
- 🔊/🔇 靜音按鈕
- 載入完成後地圖概覽動畫（縮小 2 秒看全部寶藏）→ 3-2-1 倒數
- 10 秒超時顯示「跳過」按鈕（無碰撞模式）
- window blur 清除按鍵（避免 alt-tab 後卡鍵）
- Recenter 按鈕（偏離 >300m 顯示）
- **道具系統**：每 4 秒出現（最多 **10** 個），存在 40 秒；**5 種各 20% 機率**：⚡ 加速×2（5秒）/ ⭐ 無敵+AI逃跑+穿牆（5秒）/ 🔍 廣域×3（10秒）/ ❄️ 冰凍所有AI（7秒）/ 🧲 磁鐵自動收集（8秒）
- **冰凍道具**：凍結期間 AI 停止移動和攻擊，marker 套用 CSS `hue-rotate(150deg)` 變藍色；解凍時自動還原
- **AI 逃跑**：`invincTimer > 0` 時 AI 反向遠離玩家（直接用反向向量，不跑 A*），星星期間可反擊圍剿
- **無敵穿牆修正**：`tickEffects` 偵測 `wasInvinc && invincTimer===0` 轉換，呼叫 `ensureOutsideBuilding()` + 同步 marker，防止穿牆後卡在建築物內
- **下波倒數**：chip-ai 顯示 `▲Xs` 倒數，讓玩家知道下一隻何時出現
- **廣域道具**：`effectiveR()` 動態計算有效收集半徑（CLCT_R 或 CLCT_R×3），影響 `pCircle`、`nearbyRing`、collectNearest、collect 的距離判斷
- **AI追跡者（多隻）**：第 25s 第一隻出現；之後每 60s 追加一隻，最多 3 隻；各 AI 以 aiList 陣列管理，A* 路徑錯開 0.5s 間距規劃；被抓 -50分，CD 8秒；無敵免疫
- **🎯 誘餌信號彈**：Q 鍵在玩家位置放置誘餌 marker；所有 AI 立即重算路徑追誘餌（6秒）；誘餌消失後 AI 再次追玩家；40 秒冷卻；chip-decoy 顯示倒數/冷卻
- **🔥 連擊系統**：22 秒內連續收集寶藏，第 N 顆（N≥2）額外 +`(N-1)×30` 分；連擊獎勵合入 `/collect` 的 `order_bonus`；chip-combo 顯示連擊數與剩餘窗口時間；超時未收集自動重置
- **⚡ AI 定身技能**：AI 距玩家 ≤65m 且 stunCD=0 時，定身玩家 3 秒（無法移動）；所有 AI 共用 30 秒 CD（`stunCD`）；玩家被定身時顯示橘色 chip「被定身 Xs」、全屏黃色電擊光圈、玩家 marker 閃爍；無敵期間免疫；AI 與玩家同樣跳過移動判斷（`stunTimer>0`）
- **🧲 磁鐵道具**：持續 8 秒，每 0.4 秒自動收集範圍內所有寶藏（無需按 Space）；`inFlight` Set 防止同一寶藏重複 fetch
- **💎 黃金寶藏**：每 45 秒隨機選一個未收集寶藏變金色（tbadge.golden + 地圖金圈）；15 秒內收集可得 3× 分數；額外加成合入 `/collect` 的 `order_bonus`；到期或收集後自動清除
- **👁️ 巡邏守衛（patroller）**：第 2 波出現（60s 後），紫色 👁️；沿 OPTIMAL 路標按順序巡邏（A*）；視野錐形 50m 長 × 8m 半寬（L.polygon 即時更新）；玩家進入視野 -30 分（alertTimer=3s, alertCD=10s 防連觸）；警戒時圖示變紅並面向玩家暫停；不逃跑、不攻擊
- **🦹 寶物小偷（thief）多波次**：100s 第一隻出現，每 100s 追加一隻，最多 3 隻（`THIEF_MAX=3, THIEF_WAVE_INTERVAL=100`）；速度 ×1.0（等同基礎 AI_SPD，比原本 ×0.75 更快）；每隻小偷有獨立 `ai.targetMarker`，各自標示其目標寶藏；收集或搬走後立即清除對應 marker；`_updateThiefMarker(ai)` 取代舊的全局函式
- **FOV 錐形計算**：正向單位向量 `(fMX,fMY)` 在公尺空間計算；forward 投影 `fwd=dx*fMX+dy*fMY`，lateral 投影 `lat=dx*fMY-dy*fMX`；`0<fwd≤50 && |lat|≤8` → 在視野內；`updateFOVPoly` 從 apex 出發，tip±perpendicular 計算三角形頂點（lat/lon）
- **AI spawn 邏輯**：遊戲第一幀 `initialSpawnDone` 觸發，靜默生成 10 名巡邏守衛（均勻分散路標起始位置）；60s 後追跡者波次（最多3隻）；100s 後小偷波次（最多3隻）；chip-ai 動態顯示各型別數量與下波倒數
- **最佳路徑 A* 修正**：建築物載入後呼叫 `rebuildOptimalRouteAstar()`，以遊戲本地 navGrid 重新計算 START→寶藏1→...→寶藏N 的折線，取代 OSRM 路線；確保顯示的最佳路徑和 AI 實際走的路都繞開相同建築物；`routeLine`/`miniRouteLine` 改為 `let` 變數以支援後期更新
- **巡邏守衛均勻分散**：`spawnAI('patroller')` 時依已有巡邏守衛數量均勻分配 OPTIMAL 起始路標索引（`pIdx*OPTIMAL.length/10 % OPTIMAL.length`），確保 10 隻守衛分散在路線各段而非全部擠在同一起點
- **定身只凍玩家**：`tickAI` 中 AI 的跳過條件只保留 `aiFrozenTimer>0`（❄️ 冰凍炸彈），移除 `stunTimer>0`；定身時 AI 繼續移動，只有玩家的 WASD 被 `if(stunTimer===0)` 鎖住；定身觸發已移至 `tickPatroller`
- **collect() 座標修正**：最上方 `tCurrent=TREASURES.find(...)` 覆蓋 tLat/tLon，確保小偷搬移後距離判斷正確；成功後掃描 aiList 清除 thief.targetTId
- **applyScorePenalty(amount,msg)**：統一扣分邏輯（原 chaser 攻擊 inline 程式碼也已改用此函式）
- **距離計分**：app.py 在 start_game 時依 `haversine(start, treasure)` 計算各寶藏分數（50~500，四捨五入到10），越遠越高
- 橋梁/空橋/隧道排除碰撞：`bridge=yes`、`man_made=bridge`、`tunnel=yes`、`building=bridge/passage`、`layer≥1` 均排除

---

### templates/finish.html

```html
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <title>遊戲結束</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: Arial, sans-serif; background: #f0f4f8; min-height: 100vh; }
        .hero { text-align: center; background: linear-gradient(135deg, #34a853, #1a73e8);
                color: white; padding: 50px 20px; }
        .hero h1 { font-size: 2.5rem; margin-bottom: 10px; }
        .container { max-width: 600px; margin: 40px auto; padding: 0 20px; }
        .card { background: white; border-radius: 12px; padding: 30px;
                box-shadow: 0 2px 12px rgba(0,0,0,0.1); margin-bottom: 24px; }
        .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px; }
        .stat { text-align: center; padding: 20px; background: #f5f5f5; border-radius: 10px; }
        .stat .num { font-size: 2.5rem; font-weight: bold; color: #1a73e8; }
        .stat .label { font-size: 13px; color: #666; margin-top: 4px; }
        .back-btn { display: block; text-align: center; padding: 14px;
                    background: #1a73e8; color: white; text-decoration: none;
                    border-radius: 8px; font-size: 16px; font-weight: bold; }
        .back-btn:hover { background: #1558b0; }
        table { width: 100%; border-collapse: collapse; }
        th { background: #f5f5f5; padding: 10px; text-align: left; font-size: 14px; color: #555; }
        td { padding: 10px; border-bottom: 1px solid #eee; font-size: 14px; }
    </style>
</head>
<body>
    <div class="hero">
        <h1>
            {% if found_count == total %}🎉 完美通關！
            {% elif found_count >= total // 2 %}🌟 表現不錯！
            {% else %}💪 繼續加油！{% endif %}
        </h1>
        <p>{{ player.name }} 的冒險結束了</p>
    </div>
    <div class="container">
        <div class="card">
            <div class="stats">
                <div class="stat"><div class="num">{{ player.score }}</div><div class="label">總分</div></div>
                <div class="stat"><div class="num">{{ found_count * 100 }}</div><div class="label">寶藏分（×100）</div></div>
                <div class="stat"><div class="num" style="color:#f9a825">+{{ time_bonus }}</div><div class="label">時間獎勵</div></div>
                <div class="stat"><div class="num">{{ player.elapsed_time | round(0) | int }}s</div><div class="label">用時</div></div>
            </div>
            <p style="font-size:12px;color:#888;margin-bottom:16px;text-align:center">
                計分公式：每個寶藏 100 分 + 剩餘秒數 × 1（時間獎勵）
            </p>
            <a href="/" class="back-btn">🔄 再玩一次</a>
        </div>
        {% if top10 %}
        <div class="card">
            <h2 style="margin-bottom:4px">🏆 {{ city }} 排行榜</h2>
            <p style="font-size:12px;color:#888;margin-bottom:14px">同城市玩家最高分</p>
            <table>
                <tr><th>名次</th><th>玩家</th><th>分數</th><th>寶藏</th><th>時間</th></tr>
                {% for s in top10 %}
                <tr style="{% if s.name == player.name and s.score == player.score %}background:#e8f5e9{% endif %}">
                    <td>{% if loop.index==1 %}🥇{% elif loop.index==2 %}🥈{% elif loop.index==3 %}🥉{% else %}{{ loop.index }}{% endif %}</td>
                    <td>{{ s.name }}</td><td><b>{{ s.score }}</b></td>
                    <td>{{ s.treasures }}</td><td>{{ s.time }}s</td>
                </tr>
                {% endfor %}
            </table>
        </div>
        {% endif %}
    </div>
</body>
</html>
```

---

## 8. 技術架構筆記

### API 超時與鏡像策略

```
Overpass 鏡像（依序嘗試，任一成功即回傳）：
  1. overpass.kumi.systems      timeout: 8s（POI）/ 10-12s（建築物）
  2. overpass.openstreetmap.ru
  3. overpass-api.de

快取：MapAPI._road_cache（class-level dict）
  key = (round(lat,2), round(lon,2)) 或 (round(s,3),...bbox...)
  效果：同城市第二次進入「瞬間回應」
```

### Session Cookie 限制

Flask session 存在 cookie（上限 4093 bytes）。
**不可**把 map HTML 或大型 JSON 存進 session，只存：
```python
session["player"]        # 玩家狀態 dict
session["treasures"]     # 5 個寶藏 list
session["optimal_order"] # 5 個 id list
```

### 建築物碰撞演算法

```
1. 空間格（Spatial Grid）：GRID_DEG=0.001°（≈110m），loadBuildings 建立後，
   isInBuilding 只查玩家所在格的建築，從 O(n) 降至 O(幾十)
2. Bounding box 預篩：O(1) 排除明顯不相交的建築（格內二次篩選）
3. Ray Casting（point-in-polygon）：計算射線穿越多邊形邊數
4. 多邊形簡化：>24 頂點時 step 抽稀至 20 點
5. 上限：最多 3500 棟
6. 滑牆：對角線移動被擋時，嘗試純 X 或純 Y 軸移動
7. 橋梁/空橋/隧道過濾：_parse_map_data 中跳過具有以下特徵的 way：
   bridge=yes、man_made=bridge、tunnel=yes、building=bridge/passage、layer≥1
   確保玩家可以在橋上、空橋走廊自由移動
```

### Overpass 建築物查詢策略（瀏覽器直連 + 伺服器備援）

```
前端 fetchBuildingsDirect（game.html）：
  - 同時向 3 個 Overpass 鏡像 POST（無 Promise.any，相容所有瀏覽器）
  - AbortController 硬限 17s，第一個成功的鏡像獲勝，其餘中止
  - 查詢 6 個焦點點（出發點＋5寶藏），半徑 0.0013°（約 140m）
  - Overpass query timeout: 16s

localStorage 快取（fetchBuildingsCached）：
  - key = bld_{bbox_coarse}，TTL 24 小時
  - 同城市第二次進入瞬間載入

伺服器備援（/roads?pts=...）：
  - 瀏覽器直連失敗（返回 []）時觸發
  - fetch 帶 AbortController 25s timeout
  - 伺服器呼叫 fetch_roads_focused()，並行鏡像最多等 24s

後端 fetch_roads_focused（map_api.py）：
  - 半徑 0.0013° focus-point union 查詢
  - _parallel_post() 並行 3 鏡像，per_timeout=22s，total_timeout=24s
  - 結果存入 MapAPI._road_cache
```

### A* 路徑規劃（AI 追跡者）

```
buildNavGrid()：在 loadBuildings 結束時呼叫
  - 遍歷 BOUNDS 內每個 NAV_CELL(0.0004°≈44m) 格的中心
  - 呼叫 isInBuilding() → 存入 Uint8Array（0=可走 / 1=阻擋）
  - 格數：約 (lat範圍/0.0004) × (lon範圍/0.0004)，典型 50×50=2500 格

runAstar(fromLat,fromLon,toLat,toLon)：
  - MinHeap（binary heap）保持 f=g+h 最小元素優先
  - 允許 8 方向移動（對角線 cost=1.414）
  - closed set 防止重複處理
  - MAX_NODES=3000，超出時回傳 [] → AI 直走
  - 路徑點每隔一個取一個（+保留最後）減少微步驟

tickAI(dt)：
  - 每 1.5s 呼叫 runAstar 更新 aiPath（只靠計時器，不每幀觸發）
  - 跳過已到達的路徑點（閾值 30m）
  - 直接向目標路徑點移動（無 isInBuilding 中途檢查，A* 保證可走）
  - aiPath 耗盡時直線追玩家（備援，等下次重算）
  - aiAttackCD 先設再判無敵，避免無敵期間每幀觸發 toast

spawnAI()：
  - 生成候選位置後呼叫 nearestWalkable() 移到最近可走格
  - 確保 AI 不會生成在建築物內部卡住
```

### 幀節流系統（Frame Throttling）

```
目的：避免每幀（~60fps）執行 900+ DOM 操作導致低階裝置卡頓

frameCount++ 每幀遞增
uiFrame = (frameCount % 4 === 0)  → 約 15fps，用於 DOM 更新
aiFrame = (frameCount % 2 === 0)  → 約 30fps，用於 AI marker + map.setView

DOM 操作一律包在 if(uiFrame){...}：
  - tickSprint 的 sprint bar/label/dot
  - tickEffects 的所有 getElementById/style/display/textContent
  - tickItems 的 warn class 與 opacity
  - tickAI chip 更新
  - updateMiniMap / updateDistances（在 loop() 末尾 if(uiFrame) 呼叫）

map.setView 在 tryMove() 末尾：if(aiFrame) map.setView(...)
AI marker setLatLng 在 loop 末尾：if(aiFrame){ for(const ai of aiList){...} }

item._badgeEl 快取道具的 DOM element，避免每幀重複查詢
```

### 非同步 A*（Async A*）

```
問題：runAstar 在密集城市耗時 5-20ms，每幀呼叫阻塞主線程

解法：(requestIdleCallback||setTimeout)(()=>{ ai.path=runAstar(...); ai._astarPending=false; })
  requestIdleCallback：瀏覽器空閒幀執行，不佔用動畫幀
  setTimeout：Safari 後備（不支援 requestIdleCallback）

ai._astarPending flag：
  - 為 true 時跳過 pathTimer 到期的重排程，防止 A* 堆積
  - 必須在以下情況重置：A* callback 完成、dropDecoy()、tickDecoy() 到期
  - 若只重置 pathTimer 而忘記重置 _astarPending，A* 永遠不再執行（已修正）
```

### 排行榜 GitHub API 持久化

```
問題：Render 免費方案磁碟 ephemeral，每次部署重新部署後 data/scores.json 消失

解法：用 GitHub Contents API 把 scores.json 存在 repo 本身

流程：
  啟動 → _gh_load() 讀 scores.json → 拿到 (scores, sha)
  存分 → _gh_save(scores, sha) 寫回 → 再次 _gh_load() 更新 sha
  失敗 → 靜默；本機檔案作為備用讀取來源

注意：
  - .gitignore 加了 scores.json，本機 git 不會推覆蓋 API 管理的版本
  - 若 git push 在 GitHub API 寫入後執行，需先 git pull --rebase origin master
  - GITHUB_TOKEN 需在 Render Dashboard > Environment Variables 設定
```

### 按鍵系統（Key System）

```
keys[e.key] = true   on keydown
delete keys[e.key]   on keyup

clearAllKeys()：delete keys[k] for all k
  觸發時機：blur、visibilitychange(hidden)、focus
  遊戲每幀：if(!document.hasFocus()) clearAllKeys()

目的：cloudflare tunnel / alt-tab / OS 視窗切換時 keyup 不觸發
  → key 殘留 → 角色持續移動（飄移）
  → clearAllKeys 確保失焦後停止

不用 timestamp 方案原因：
  Shift 鍵 OS repeat delay 可達 500ms+，timestamp 超時導致衝刺誤判為放開
```

### WSL2 網路

```
Flask 必須 host="0.0.0.0"
Windows 瀏覽器用 WSL2 IP（例如 172.18.227.118:5000）
固定 secret_key 避免 Flask 重啟後 session 失效
```

### 前端移動速度換算

```
1 度緯度 ≈ 111,000m
WALK_SPD  = 0.00025 度/幀 × 111000 = 27.75 m/s（含 dt 所以實際依幀率）
SPRINT_SPD = 0.00050 度/幀 × 111000 = 55.5 m/s
dt clamped to 0.05s（避免 tab 失焦後大 dt 造成穿牆）
```
