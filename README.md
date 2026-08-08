# 中文

## 願浮沉2:無火戰爭 — 後端 API

劇本殺遊戲輔助工具「願浮沉2:無火戰爭」的後端 API。這份文件分成兩個獨立的部分，請依需求閱讀:

- **[專案報告](#專案報告)**:這個系統是什麼、怎麼串起來的、用了哪些技術與決策 —— 給想了解「這是什麼」的人看。
- **[架設 SOP](#架設-sop)**:一步一步的操作說明 —— 給想「動手把它跑起來」的人看。

這兩部分刻意分開，不要交叉閱讀;報告是背景知識，SOP 是操作手冊。

---

## 專案報告

### 這是什麼

「願浮沉2:無火戰爭」是一個 MMP(謀殺之謎，又稱劇本殺)的game master 輔助網站。遊戲的核心資料(五位角色的事業等級、金錢、積分等)存在 Google Sheet 裡，主持人透過網頁輸入場次的日期時間，系統會讀取(或協助建立)對應的 Sheet 檔案，並把裡面的數字整理成長條圖、總覽數據，取代主持人自己在 Sheet 裡人工核對的過程。

### 系統架構

整個專案是一個 git meta-repo(`fireless-war`)透過 submodule 掛載兩個獨立 repo:

```
fireless-war/                    ← meta-repo，本機開發統一入口，本身不部署
├── fireless-war-backend/        ← 本 repo，部署到 Render(Flask + gunicorn)
└── fireless-war-web/            ← 部署到 GitHub Pages(純靜態 HTML/CSS/JS)
```

資料源頭是 Google Sheets(每場遊戲一份獨立檔案，複製自共用的 Template)，後端用 Service Account 身分唯讀存取。前端完全是 vanilla JavaScript，沒有任何前端框架或建置流程，直接把 `.html`/`.css`/`.js` 丟給 GitHub Pages 服務。

### 後端技術棧與關鍵決策

Flask + gunicorn，部署在 Render 免費方案。主要相依套件見 `requirements.txt`:`Flask`、`Flask-Cors`、`Flask-Limiter`、`gunicorn`、`gspread`、`google-auth`、`requests`。

#### Google Sheets 存取

用 `gspread` + Service Account 憑證唯讀存取。Google Sheets API 配額是「每個 Service Account 身份每分鐘 60 次讀取」，因此所有讀取都合併成單次 `values_batch_get` 呼叫(見 `cloud_utils/sheet_access.py`)，而不是逐格分開打 API——`/round` 原本要打 8 次 API，合併後只需要 1 次。`/round` 另外掛了 Flask-Limiter 的**全站共用**(不分 IP、不分主持人)`30 次/分鐘`限制，因為要保護的是全站共用的單一 Service Account 配額，不是防止單一使用者太活躍。這個限制只對**通過驗證的請求**扣額度(`deduct_when`)——Flask-Limiter 的檢查發生在身分驗證之前，如果連未登入的 401 都算進去，任何不需要密碼的陌生人都能靠灌爆這個共用額度，把所有主持人鎖在門外一整分鐘。

#### 建立新場次檔案:為什麼要繞一圈用 Apps Script

一開始想直接用 Service Account 呼叫 Google Drive API 複製 Template，但兩條路都走不通:
1. Service Account 直接 `copy()`:報 `storageQuotaExceeded`——Service Account 沒有自己的 Drive 儲存額度，無法擁有新建立的檔案，這是 Google 對這種身分類型的結構性限制。
2. 改用 OAuth(代表真人帳號)+ Google Picker:理論上能繞開額度問題，但實測下來，Picker 選取既有檔案後的授權登記一直沒有生效(`files.get` 持續回 404)，原因不明，排查多輪後放棄。

最後採用的方案:寫一支 **Google Apps Script**，部署成 Web App，Flask 用 HTTP 請求呼叫它。Apps Script 執行時用的是**你自己的 Google 帳號**完整權限，不受上述兩個限制影響，`DriveApp.makeCopy()` 是 Google 原生的複製動作，公式、格式都完整保留。

**這支 Apps Script 程式碼不在這個 git repo 裡**——它只存在於 Google 自己的 Apps Script 編輯器(script.google.com)，透過網頁介面編輯與部署，不會被這裡的 `pip install` 或 Render 部署動到。

#### Google 登入驗證

主持人的身分驗證，原本是最陽春的「前端自己填 email、後端比對白名單」，任何人只要知道某位主持人的 email 字串就能冒充。現在改用真正的 Google 登入:前端用 Google Identity Services(GIS)取得使用者登入後的 ID Token(JWT)，每次呼叫 API 都夾帶 `Authorization: Bearer <token>`;後端(`auth_utils/auth.py`)用 `google-auth` 套件驗證這個 token 的簽章、有效期限、以及 audience(確認是發給我們自己這個 OAuth Client ID，不是別人專案的 token)，驗證通過後拿到「Google 保證過的」email，再比對白名單。整個流程無法被瀏覽器 devtools 繞過，因為驗證發生在後端，不是前端自己判斷要不要放行。

後端刻意區分兩種「驗證沒過」:token 真的無效/過期回 `401`;連不上 Google 拿公開金鑰之類的暫時性故障回 `503`。這兩種前端的處理方式完全不同——只有 `401` 才會把使用者登出、清掉 token。這是因為 `currentIdToken` 一旦被清空,45 分鐘那次靜默續期的排程(條件是 `if (currentIdToken)`)就會永久停止,而登入列在第二頁之後是隱藏的,使用者連重新登入的入口都看不到。所以前端遇到網路失敗或 `503` 時,會保留 token、鎖住讀取按鈕,並以指數退避(5 秒→60 秒上限)自動重試,而不是直接判定登入失效。

#### 主持人白名單

白名單(`auth_utils/gm.py`)從 `PERMITTED_USER` 環境變數讀取(逗號分隔的 email 清單)，不寫死在程式碼裡——這份清單是真實個人資料，不該進版本控制，尤其這個 repo 是 Public。沒設定這個環境變數時，視為空清單，也就是沒有任何人被授權，這是刻意的安全預設值(壞掉時關閉存取，而不是不小心開放給所有人)。要開放給新的主持人使用，不用改程式碼、不用 push:去 Render 後台的 Environment 設定編輯這個變數即可，存檔後自動重新部署套用新值。

#### 其他安全性強化

- **CORS**:限制只允許 GitHub Pages 正式網域 + 本機開發的 localhost/127.0.0.1(任意 port)呼叫，並明確放行 `Authorization` header(沒有這行，瀏覽器的 CORS 預檢會擋下這個 header)。
- **SRI(Subresource Integrity)**:前端引入的 Chart.js / chartjs-plugin-datalabels CDN script 都加了 SRI hash，防止 CDN 被竄改後注入惡意程式碼(Google Identity Services 的 script 刻意不加，因為它的內容本來就會隨時變動)。

#### Render 免費方案的 Keep-Alive

Render 免費方案閒置約 15 分鐘會休眠，喚醒(cold start)可能要 30~90 秒以上。用 `.github/workflows/keep-alive.yml` 這個 GitHub Actions cron，每 10 分鐘打一次 `/status`，讓服務保持清醒。選擇 GitHub Actions 而不是 UptimeRobot 之類的外部服務，是因為這個 repo 是 Public——Public repo 的 Actions 分鐘數是免費無上限的，若是 Private repo，這個頻率會超過每月 2000 分鐘的免費額度(GitHub 每次執行至少計費 1 分鐘，10 分鐘一次 ≈ 每天 144 次 ≈ 每月超過 4000 分鐘)。

後來發現 GitHub Actions 的 `schedule` 觸發**不保證真的照設定的頻率執行**——實測 `gh run list` 顯示，雖然設定是每 10 分鐘，實際間隔卻常常拉長到 1~4 小時以上(GitHub 官方文件本身也承認 schedule 觸發「可能因系統負載而延遲」)，遠超過 Render 15 分鐘的休眠門檻，冷啟動因此還是會在遊戲進行中發生。真正解決這個問題的是前端(`fireless-war-web/script.js`)自己加的 heartbeat:只要分頁還開著，一載入就先打一次 `/status`，之後每 5 分鐘再打一次，不依賴任何外部排程器的時間精準度——只要主持人在玩，分頁就不會讓後端閒置超過 15 分鐘。GitHub Actions 的 cron 依然保留當作次要備援(還是會不定期觸發，只是不能單獨依賴它)。

#### 檔案結構

程式碼依職責分成四個套件，`app.py`(路由入口)留在根目錄:

```
app.py                 路由(gunicorn 的啟動目標)
configs/config.py       集中管理設定值與環境變數
cloud_utils/            Google Sheet/Drive 存取層，只知道怎麼跟 API 對話，不理解資料的業務意義
  ├── sheet_access.py    Sheet「內容層級」
  └── drive_access.py    Drive「檔案層級」
data_utils/              業務邏輯層，知道 A~J 欄分別代表什麼、檔名怎麼組
  ├── parse_data.py       回合資料解析與計算
  └── record_data.py      場次檔案查詢與建立
auth_utils/              Google 登入驗證與主持人白名單
  ├── auth.py             ID Token 驗證
  └── gm.py               白名單查詢
```

### 前端技術棧與關鍵決策

Vanilla JavaScript(無框架、無建置流程)，`Chart.js` + `chartjs-plugin-datalabels` 畫長條圖，Google Fonts 的 Noto Sans TC 作為主字型，整站部署在 GitHub Pages(Free 方案要求 repo 是 Public 才能開啟 Pages 功能)。

#### 三頁式流程

1. **第一頁**:輸入日期時間 → `GET /record` 查詢對應的場次 Sheet 是否存在。找到就直接進第二頁;找不到則詢問是否要 `POST /record` 建立新場次(複製自 Template)。
2. **第二頁**:開場介紹畫面(「為期七日」「無火戰爭」+「正式開始!」按鍵)，純粹的轉場頁，不會在這裡打任何 API——按下按鍵才會去抓資料進第三頁。
3. **第三頁**:長條圖總覽——五位角色各自的事業等級長條圖、持有金錢/積分、共同數據面板(合法/非法事業加總、風頭事業指標、崩壞警示)，搭配底部的回合切換器(水平滾輪選擇器，15 個回合選項)。

#### 資料視覺化邏輯

每位角色的五項事業(正當事業/闇金/色情/毒品/軍火)畫成長條圖，Y軸固定 0–25。三個全域轉換開關(`oniwara_out`/`mike_out`/`kouno_single`)會改變顯示邏輯——例如 `oniwara_out=true` 時，鬼原響介的事業「洗白」，顯示名稱與計入合法/非法事業的方式都會改變。共同數據面板會即時判斷「合法事業 vs 非法事業」的差距，超過閾值顯示崩壞警示;若 `Global_Param!B10` 開關開啟，額外計算並顯示「風頭事業」(非法事業四類加總最高者，同分時毒品優先於金融、軍火、色情)。

#### Google 登入 UI

登入狀態只在第一頁顯示，進入第二頁後自動隱藏。session 完全不做 client-side 持久化(沒有用 localStorage/cookie 存 token)——重新整理後靠 Google Identity Services 的靜默重新登入(`prompt({auto_select:true})`)嘗試無感恢復，如果瀏覽器裡有多個 Google 帳號同時登入，Google 會要求手動選一次帳號(這是 Google 平台自身的隱私限制，無法繞過)。刻意不做本機持久化的原因:如果存了 token，主持人被從白名單移除後，舊分頁可能要等 token 真的過期才會感覺到權限被收回;不存，才能保證後端白名單一改，下次重新整理立刻生效。

### 資料流程總覽

主持人登入 → 輸入日期時間 → `GET /record`(帶 Bearer token)查詢場次檔案 → 找到 `spreadsheet_id` 或建立新檔案 → 進入介紹頁 → 按「正式開始!」→ `GET /round`(帶 `spreadsheet_id` + Bearer token)一次性 batch 讀取該回合所有資料 → 前端渲染長條圖與共同數據 → 之後每次用底部的回合切換器換回合，重複呼叫 `GET /round`。

### 已知限制

`oniwara_out`/`mike_out`/`kouno_single` 三個轉換開關、以及「城市經濟崩壞」這個最嚴重等級的警示，目前都只用合成測試資料驗證過邏輯，還沒在真實遊戲中實際觸發驗證過;`最終結算`(FinalDayResult)這個回合是否要有特殊畫面表現，尚未決定;`GET /round?spreadsheet_id=` 目前不會驗證這個 ID 是不是「合法建立過的場次檔案」，理論上帶入任意公開 Sheet ID 也會嘗試讀取。

---

# 架設 SOP / Setup Guide

## Part A. 先在你的 Mac 上本機測試(確認程式本身沒問題)

### 1. 確認你有 Python

打開「終端機」(Terminal),輸入:

```bash
python3 --version
```

如果有顯示版本號(例如 `Python 3.11.x`),代表你已經有 Python,可以跳到步驟2。
如果顯示「command not found」,先到 https://www.python.org/downloads/ 下載安裝。

### 2. 進入專案資料夾，建立「虛擬環境」

虛擬環境是什麼:簡單說，是幫這個專案獨立準備一個「乾淨房間」,裝的套件不會跟你電腦上其他 Python 專案打架。

```bash
cd 你解壓縮後的資料夾路徑/fireless-war-backend
python3 -m venv venv
source venv/bin/activate
```

執行完 `source venv/bin/activate` 後，你會看到終端機提示字元前面多了 `(venv)`,代表虛擬環境啟動成功。

### 3. 安裝套件

```bash
pip install -r requirements.txt
```

### 4. 本機啟動伺服器

```bash
python3 app.py
```

看到類似這樣的訊息代表成功:

```
* Running on http://127.0.0.1:5001
```

> 註:這裡故意不用 5000,是因為 macOS 的 AirPlay 接收器功能常常佔用 5000 port,改用 5001 可以避開衝突，不需要去系統設定關閉 AirPlay。

> 註:單純啟動伺服器、測試 `/status`,不需要任何環境變數或 Google 憑證。但只要牽涉到讀 Google Sheet 或建立場次檔案的 API(`/round`、`/record`),就需要先準備好 `credentials/service_account.json`(Service Account 金鑰檔)以及下方「環境變數總覽」列出的變數。

### 5. 測試 `/status`(開另一個終端機分頁，或直接用瀏覽器)

瀏覽器打開:`http://127.0.0.1:5001/status`

應該會看到:
```json
{"status": "ok", "message": "Fireless War backend is running"}
```

看到這個，代表程式本身沒問題，可以進入 Part B 部署到 Render。

按 `Control + C` 可以停止本機伺服器。

---

## Part B. 部署到 Render(讓這支 API 有一個網址，任何人都能連到)

### 1. 把專案傳到 GitHub(Render 需要從 GitHub 讀取程式碼來部署)

如果你還沒有這個專案的 GitHub repo:

```bash
git init
git add .
git commit -m "Initial commit"
```

接著到 https://github.com/new 建立一個新的 repository,建立好之後，GitHub 會顯示指令，大致像這樣(依你畫面顯示的為準):

```bash
git remote add origin https://github.com/你的帳號/fireless-war-backend.git
git branch -M main
git push -u origin main
```

> 註:這個 repo 目前是 **Public**,是刻意的選擇——原因之一是 GitHub Actions 的分鐘數對 Public repo 免費無上限(見下方 Keep-Alive 說明),原因之二是作品集展示用途。真正敏感的資料(Service Account 金鑰、Apps Script 密語、主持人白名單)全部走環境變數或 `.gitignore`,不會因為 repo 公開而外洩。如果你有不同考量想設為 Private,務必重新檢查 keep-alive 排程的 Actions 分鐘數是否還在免費額度內。

### 2. 到 Render 建立 Web Service

1. 到 https://render.com 註冊/登入(可以直接用 GitHub 帳號登入，比較快)
2. 點右上角 **New +** → **Web Service**
3. 選擇「Connect a repository」,授權 Render 存取你的 GitHub,選擇剛剛建立的 `fireless-war-backend`
4. 填寫設定:
   - **Name**:自訂，例如 `fireless-war-backend`
   - **Region**:選 Singapore(離台灣最近，之後接資料庫也建議選同區域)
   - **Branch**:`main`
   - **Runtime**:Python 3
   - **Build Command**:`pip install -r requirements.txt`
   - **Start Command**:`gunicorn app:app --bind 0.0.0.0:$PORT`
     (Render 會用環境變數 `$PORT` 指定實際要用的 port,這行指令是告訴 gunicorn 要監聽那個 port,不能省略，不然部署後連不進去)
   - **Instance Type**:選 **Free**
5. 到 **Environment** 分頁，依下方「環境變數總覽」把需要的變數都設定好(至少要有 `PERMITTED_USER`,不然沒有任何人能通過登入驗證)
6. 點 **Create Web Service**

Render 會開始自動建置，這個過程約 1~3 分鐘，你可以在畫面上看到即時的部署 log。

> 註:Render 免費方案閒置約 15 分鐘會進入休眠，喚醒可能要 30~90 秒以上。專案裡的 `.github/workflows/keep-alive.yml` 會每 10 分鐘自動打一次 `/status` 防止休眠，不需要額外設定，repo push 上去、GitHub Actions 啟用後就會自動生效。

### 3. 部署完成後測試

Render 會給你一個網址，長得像:
```
https://fireless-war-backend.onrender.com
```

瀏覽器打開:
```
https://fireless-war-backend.onrender.com/status
```

看到 `{"status": "ok", ...}` 就代表基本部署成功了。

---

## Part C. 環境變數總覽

| 變數名稱 | 必填? | 說明 |
|---|---|---|
| `PERMITTED_USER` | **必填** | 逗號分隔的主持人 email 清單，例如 `a@gmail.com,b@gmail.com`。不設定 = 空清單 = 沒有任何人能登入，這是刻意的安全預設值。 |
| `APPS_SCRIPT_URL` | **必填**(要用到 `POST /record` 才需要) | 部署 Apps Script Web App 後拿到的網址，結尾是 `/exec`。見 Part D。 |
| `APPS_SCRIPT_SECRET` | **必填**(同上) | 跟 Apps Script 裡 `SECRET` 常數完全一致的密語，用來擋掉沒有這組密語的請求。 |
| `DRIVE_FOLDER_ID` | **必填**(同上) | 場次檔案所在的 Drive 資料夾 ID,`GET /record` 查詢時會用到。 |
| `CREDENTIALS_PATH` | 選填 | Service Account 金鑰檔路徑，預設 `credentials/service_account.json`。本機開發用檔案路徑;Render 上通常改用 Render 的 Secret File 功能掛載。 |
| `SPREADSHEET_ID` | 選填 | 沒帶 `spreadsheet_id` 參數時的 fallback 測試檔案，只有本機開發測試會用到。 |
| `GOOGLE_CLIENT_ID` | 選填 | Google OAuth Client ID,驗證前端傳來的 ID Token 用。這不是密鑰，程式裡有寫死一組預設值，通常不需要覆蓋。 |

本機測試前記得先 `export` 這些值，例如:

```bash
export PERMITTED_USER="你的Google帳號email@gmail.com"
export APPS_SCRIPT_URL="https://script.google.com/macros/s/AKfycb.../exec"
export APPS_SCRIPT_SECRET="你的密語"
export DRIVE_FOLDER_ID="你的資料夾ID"
```

---

## Part D. 測試需要登入驗證的 API(`/record`、`/round`)

Part A 的 `/status` 沒有驗證，可以直接用瀏覽器網址列打開;但 `/record` 和 `/round` 現在都需要在請求的 `Authorization` header 帶一個有效的 Google ID Token,瀏覽器網址列沒辦法附加自訂 header,不能像 `/status` 那樣直接測試。

本機測試的兩種方式:

1. **透過真正的前端走完整流程(推薦)**:把 `fireless-war-web` 用本機靜態伺服器跑起來，完成 Google 登入，前端會自動帶上正確的 token。
2. **手動用 curl 測試**:先透過前端登入拿到 token(瀏覽器開發者工具的 Network 分頁，複製任一個成功請求的 `Authorization` header 值),再帶入 curl:

```bash
curl -H "Authorization: Bearer <你複製到的 ID Token>" \
  "http://127.0.0.1:5001/round?day=1st&type=Morning"
```

沒帶 token,或 token 對應的 email 不在 `PERMITTED_USER` 名單裡，都會回傳 `401`。

**`/round` 回應格式範例**(讀取真實遊戲資料時的實際結構):

```json
{
  "day": "1st",
  "type": "Morning",
  "round_label": "第一天財報",
  "oniwara_out": false,
  "mike_out": false,
  "kouno_single": false,
  "legal_business": 52,
  "illegal_business": 54,
  "broken_target": 30,
  "business_level": {
    "oniwara": {
      "organization": "鬼原一家",
      "general_business": 8, "finance": 3, "sex": 1, "drug": 0, "arms": 6,
      "owned_money": 54, "current_integral": 123
    }
  },
  "kiyoshiro_escape": false,
  "hot_business": null
}
```

（`business_level` 實際上會有 `oniwara`/`mike`/`kinugawa`/`kouno`/`ph003` 五位角色，這裡只列一位當範例。）

如果 `day` 或 `type` 打錯(例如 `day=8th`),會回傳 `400` 錯誤，並附上清楚的錯誤訊息告訴你合法值有哪些。

**`/record` 用法**:

```
GET /record?datetime=2026_07_01_18_30
```
- `200`:找到，回傳 `{"spreadsheet_id": "..."}`
- `404`:查無此檔案(前端可據此詢問使用者是否要建立新場次)
- `400`:`datetime` 格式不合法(應為 `YYYY_MM_DD_HH_MM`)

```
POST /record?datetime=2026_07_01_18_30
```
- `201`:建立成功，回傳 `{"spreadsheet_id": "..."}`
- `500`:建立失敗(例如 Apps Script 連不上、密語不對、Drive 發生問題)
- `400`:`datetime` 格式不合法

拿到 `spreadsheet_id` 後，之後每次呼叫 `/round` 都要附帶這個參數，後端是無狀態設計，不會自己記住「目前是哪一場」:

```
GET /round?day=1st&type=Morning&spreadsheet_id=abc123...
```

不帶 `spreadsheet_id` 時，會 fallback 用 `SPREADSHEET_ID` 環境變數(本機測試用的預設檔案)。

---

## 關於 `gunicorn app:app` 這個指令(補充，不影響操作)

`app.py` 是本機測試用的簡易啟動方式，正式上線環境會用 `gunicorn`(一個更穩定、能處理多個請求的伺服器程式)。`app:app` 的意思是「去 `app.py` 這個檔案裡，找一個叫做 `app` 的 Flask 物件來啟動」。這行你不用背，照抄設定即可。

---

# English

This is the backend API for *Dreaming of a damp squib 2 - Fireless War 2*, a murder mystery game companion tool. This document is split into two independent parts — read whichever fits what you need:

- **[Project Report](#project-report)**: what this system is, how it's wired together, and what technologies/decisions were used — for anyone who wants to understand "what is this."
- **[Setup Guide](#setup-guide)**: step-by-step operating instructions — for anyone who wants to "get it running."

These two parts are deliberately kept separate — don't read them interleaved; the report is background knowledge, the SOP is an operating manual.

## Project Report

### What This Is

*Dreaming of a damp squib 2 - Fireless War* is a game-master companion web app for a Murder Mystery Game. The game's core data (five characters' business levels, money, and integral points) lives in a Google Sheet. The GM enters a session's date/time on the web page, the system finds (or helps create) the matching Sheet file, and renders the numbers as bar charts and summary panels — replacing manual cross-referencing inside the spreadsheet.

### System Architecture

The whole project is a git meta-repo (`fireless-war`) that wraps two independently-deployed repos via submodules:

```
fireless-war/                    ← meta-repo, unified local-dev entry point, never deployed itself
├── fireless-war-backend/        ← this repo, deployed to Render (Flask + gunicorn)
└── fireless-war-web/            ← deployed to GitHub Pages (pure static HTML/CSS/JS)
```

Data lives in Google Sheets (one independent file per game session, copied from a shared Template); the backend accesses it read-only via a Service Account. The frontend is plain vanilla JavaScript with no framework or build step — the `.html`/`.css`/`.js` files are served directly by GitHub Pages.

### Backend Stack & Key Decisions

Flask + gunicorn, deployed on Render's free tier. Key dependencies (see `requirements.txt`): `Flask`, `Flask-Cors`, `Flask-Limiter`, `gunicorn`, `gspread`, `google-auth`, `requests`.

#### Google Sheets Access

Read-only access via `gspread` with Service Account credentials. Google's Sheets API quota is 60 reads/minute per Service Account identity, so all reads within one request are merged into a single `values_batch_get` call (see `cloud_utils/sheet_access.py`) instead of one call per cell/range — `/round` used to make 8 separate API calls per request, now just 1. `/round` also carries a Flask-Limiter rate limit of 30/minute that is **global** (not per-IP, not per-GM), because the resource being protected is the shared Service Account quota itself, not any single user's activity. The limit only deducts for requests that pass authentication (`deduct_when`) — Flask-Limiter's check runs before the auth decorator, so counting unauthenticated 401s too would let any stranger with no credentials exhaust the shared budget and lock every GM out for a full minute.

#### Why Creating a New Session File Goes Through Apps Script

The first attempt was calling the Google Drive API directly with the Service Account to copy the Template, but two approaches both failed:
1. Direct Service Account `copy()`: fails with `storageQuotaExceeded` — Service Accounts have no Drive storage quota of their own and structurally cannot own newly-created files.
2. OAuth (real user identity) + Google Picker: should sidestep the quota issue, but in testing, the authorization granted after picking an existing file never actually took effect (`files.get` kept returning 404 for the picked file) for reasons never root-caused; abandoned after multiple debugging rounds.

The approach that shipped: a **Google Apps Script**, deployed as a Web App, called from Flask over HTTP. Apps Script runs with the full permissions of *your own* Google account, sidestepping both limitations above — `DriveApp.makeCopy()` is Google's native copy operation and preserves formulas/formatting.

**This Apps Script code is not part of this git repo** — it exists only inside Google's own Apps Script editor (script.google.com), edited and deployed entirely through that web interface, untouched by this repo's `pip install` or Render deploy.

#### Google Sign-In Verification

GM authentication originally worked by having the frontend self-report an email that the backend matched against a whitelist — anyone who knew a GM's email string could impersonate them. This is now real Google sign-in: the frontend uses Google Identity Services (GIS) to obtain an ID Token (JWT) after login, sent as `Authorization: Bearer <token>` on every API call. The backend (`auth_utils/auth.py`) uses the `google-auth` library to verify the token's signature, expiry, and audience (confirming it was issued for our own OAuth Client ID, not some other project's), then extracts the Google-verified email and checks it against the whitelist. This cannot be bypassed from browser devtools, since verification happens server-side, not as a frontend-decided gate.

The backend deliberately distinguishes two kinds of "verification failed": a genuinely invalid/expired token returns `401`; a transient failure (e.g. can't reach Google's public keys) returns `503`. The frontend treats these very differently — only `401` signs the user out and clears the token. Clearing `currentIdToken` would permanently stop the 45-minute silent-refresh interval (guarded by `if (currentIdToken)`), and since the top bar is hidden from page 2 onward, the user would have no visible way back in. So on a network failure or `503`, the frontend keeps the token, locks the read button, and retries on exponential backoff (5s, capped at 60s) instead of treating it as a real sign-out.

#### GM Whitelist

The whitelist (`auth_utils/gm.py`) is read from the `PERMITTED_USER` environment variable (comma-separated emails), never hardcoded — this is real personal data that shouldn't be in version control, especially since this repo is Public. When unset, it defaults to an empty list — nobody authorized — a deliberate fail-closed default. Authorizing a new GM requires no code change or push: just edit the variable in Render's dashboard, which triggers an automatic redeploy.

#### Other Security Hardening

- **CORS**: restricted to the production GitHub Pages origin plus any localhost/127.0.0.1 port for local dev, with `Authorization` explicitly allowed in preflight (without it, the browser's CORS preflight strips the header and every authenticated call fails).
- **SRI (Subresource Integrity)**: the Chart.js / chartjs-plugin-datalabels CDN `<script>` tags carry SRI hashes to guard against a compromised CDN injecting malicious code (Google Identity Services' script deliberately has none, since its content is expected to change server-side).

#### Keep-Alive for Render's Free Tier

Render's free tier sleeps after ~15 minutes idle; waking up (cold start) can take 30–90+ seconds. `.github/workflows/keep-alive.yml` is a GitHub Actions cron job that pings `/status` every 10 minutes to keep the service awake. GitHub Actions was chosen over an external service like UptimeRobot specifically because this repo is Public — Actions minutes are free and unlimited for public repos; on a private repo this frequency would exceed the 2000-free-minutes/month quota (GitHub bills a 1-minute minimum per run regardless of actual duration: a 10-minute interval is ≈144 runs/day ≈ 4000+ billed minutes/month).

It later turned out GitHub Actions' `schedule` trigger **does not guarantee it actually runs at the configured frequency** — `gh run list` showed that despite the `*/10 * * * *` config, real gaps between runs often stretched to 1–4+ hours (GitHub's own docs acknowledge schedule triggers "can be delayed during periods of high load"), far exceeding Render's 15-minute sleep threshold, so cold starts could still happen mid-session. The actual fix is a heartbeat added on the frontend (`fireless-war-web/script.js`): as long as a tab is open, it pings `/status` once immediately on load and then every 5 minutes after, independent of any external scheduler's timing precision — as long as a GM is actively playing, the tab itself keeps the backend from ever seeing 15 minutes of true idle. The GitHub Actions cron is still kept as a secondary backup (it does still fire sometimes, just not reliably enough to depend on alone).

#### File Layout

Code is split into four packages by responsibility, with `app.py` (the routing entry point) staying at repo root:

```
app.py                 routes (gunicorn's entry point)
configs/config.py       centralized settings & env vars
cloud_utils/            Sheet/Drive access layer — only knows how to talk to the APIs, not what the data means
  ├── sheet_access.py    Sheet content-level
  └── drive_access.py    Drive file-level
data_utils/              Business logic layer — knows what column A~J mean, how filenames are built
  ├── parse_data.py       round-data parsing & computation
  └── record_data.py      session-file lookup & creation
auth_utils/              Google sign-in verification & GM whitelist
  ├── auth.py             ID token verification
  └── gm.py               whitelist lookup
```

### Frontend Stack & Key Decisions

Vanilla JavaScript (no framework, no build step), `Chart.js` + `chartjs-plugin-datalabels` for bar charts, Google Fonts' Noto Sans TC as the primary typeface, deployed entirely on GitHub Pages (the free tier requires the repo be Public to enable Pages).

#### Three-Page Flow

1. **Page 1**: enter a date/time → `GET /record` checks whether the matching session Sheet exists. Found → go straight to page 2; not found → offer to `POST /record` to create a new one (copied from the Template).
2. **Page 2**: an intro splash ("為期七日" / "無火戰爭" + a "正式開始!" button) — a pure transition screen, no API call happens here; only clicking the button fetches data and advances to page 3.
3. **Page 3**: the chart-grid overview — each of the five characters' business-level bar chart, money/points, a common-data panel (legal/illegal business totals, the hot-business indicator, a collapse warning banner), plus a round switcher at the bottom (a horizontal scroll-wheel picker with 15 round options).

#### Data Visualization Logic

Each character's five business categories (general/finance/sex/drug/arms) render as a bar chart, Y-axis fixed at 0–25. Three global toggles (`oniwara_out`/`mike_out`/`kouno_single`) change display logic — e.g. when `oniwara_out` is true, Oniwara's businesses "go legitimate," changing both their display labels and how they're counted toward legal vs. illegal totals. The common-data panel evaluates the legal-vs-illegal gap live and shows a collapse warning past a threshold; if the `Global_Param!B10` toggle is on, it additionally computes and shows the "hot business" (the illegal category with the highest summed level across characters, ties broken drug > finance > arms > sex).

#### Google Sign-In UI

The sign-in UI only appears on page 1, auto-hidden from page 2 onward. Session state has zero client-side persistence (no token in localStorage/cookies) — on refresh, it relies entirely on Google Identity Services' silent re-auth (`prompt({auto_select:true})`); if multiple Google accounts are signed into the browser, Google forces an explicit account-picker click (a platform-level privacy constraint, not something the app can bypass). The deliberate choice not to persist locally: a stored token would mean a GM removed from the whitelist could keep working in an already-open tab until the token naturally expires; without persistence, a whitelist change on the backend takes effect the moment the page is refreshed.

### End-to-End Data Flow

GM signs in → enters a date/time → `GET /record` (with a Bearer token) looks up the session file → obtains a `spreadsheet_id` or creates one → intro page → clicks "正式開始!" → `GET /round` (with `spreadsheet_id` + Bearer token) batch-reads that round's full data in one call → frontend renders the charts and common-data panel → switching rounds via the bottom picker repeats the `GET /round` call.

### Known Limitations

The three global toggles (`oniwara_out`/`mike_out`/`kouno_single`) and the most severe "city economy collapse" warning tier have only been verified with synthetic test data, not yet exercised against real toggled game-sheet state. Whether the Final Day round (`FinalDayResult`) should get special display treatment is still undecided. `GET /round?spreadsheet_id=` does not currently validate that the given ID is a legitimately-created session file — any accessible Sheet ID would technically be attempted.

---

# Setup Guide

## Part A. Test Locally on Your Mac First (confirm the program itself works)

### 1. Confirm You Have Python

Open "Terminal" and run:

```bash
python3 --version
```

If it shows a version number (e.g. `Python 3.11.x`), you already have Python — skip to step 2.
If it shows "command not found," go to https://www.python.org/downloads/ and install it first.

### 2. Enter the Project Folder, Create a "Virtual Environment"

What a virtual environment is: simply put, it sets up an independent "clean room" for this project, so the packages it installs don't clash with other Python projects on your machine.

```bash
cd path/to/your/extracted/folder/fireless-war-backend
python3 -m venv venv
source venv/bin/activate
```

After running `source venv/bin/activate`, you'll see `(venv)` prepended to your terminal prompt — that means the virtual environment is active.

### 3. Install Packages

```bash
pip install -r requirements.txt
```

### 4. Start the Server Locally

```bash
python3 app.py
```

You'll know it worked when you see something like:

```
* Running on http://127.0.0.1:5001
```

> Note: 5001 is used instead of 5000 on purpose — macOS's AirPlay Receiver often occupies port 5000, so 5001 avoids the conflict without needing to turn AirPlay off in System Settings.

> Note: just starting the server and testing `/status` needs no environment variables or Google credentials. But any API that touches Google Sheets or creates session files (`/round`, `/record`) needs `credentials/service_account.json` (the Service Account key file) plus the variables listed in "Environment Variables Overview" below.

### 5. Test `/status` (open another terminal tab, or just use a browser)

Open in your browser: `http://127.0.0.1:5001/status`

You should see:
```json
{"status": "ok", "message": "Fireless War backend is running"}
```

Seeing this means the program itself is working — you can move on to Part B and deploy to Render.

Press `Control + C` to stop the local server.

---

## Part B. Deploy to Render (give this API a URL anyone can reach)

### 1. Push the Project to GitHub (Render needs to read code from GitHub to deploy)

If you don't have a GitHub repo for this project yet:

```bash
git init
git add .
git commit -m "Initial commit"
```

Then go to https://github.com/new and create a new repository. Once created, GitHub will show you commands roughly like this (follow whatever your screen actually shows):

```bash
git remote add origin https://github.com/your-username/fireless-war-backend.git
git branch -M main
git push -u origin main
```

> Note: this repo is currently **Public**, which is a deliberate choice — partly because GitHub Actions minutes are free and unlimited for public repos (see the Keep-Alive section below), and partly for portfolio purposes. Genuinely sensitive data (the Service Account key, the Apps Script secret, the GM whitelist) all go through environment variables or `.gitignore`, so none of it leaks just because the repo is public. If you have different considerations and want to make it Private, be sure to re-check whether the keep-alive schedule's Actions minutes still fit within the free quota.

### 2. Create a Web Service on Render

1. Go to https://render.com and sign up/log in (signing in with your GitHub account is faster)
2. Click **New +** in the top right → **Web Service**
3. Choose "Connect a repository," authorize Render to access your GitHub, and select the `fireless-war-backend` repo you just created
4. Fill in the settings:
   - **Name**: your choice, e.g. `fireless-war-backend`
   - **Region**: Singapore (closest to Taiwan; also recommended if you add a database later, for the same region)
   - **Branch**: `main`
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app --bind 0.0.0.0:$PORT`
     (Render provides the actual port to use via the `$PORT` environment variable; this command tells gunicorn to listen on that port — don't omit it, or the deployed service won't be reachable)
   - **Instance Type**: **Free**
5. On the **Environment** tab, set up whatever variables you need per "Environment Variables Overview" below (at minimum `PERMITTED_USER`, or nobody will be able to pass login verification)
6. Click **Create Web Service**

Render will start building automatically — this takes about 1–3 minutes, and you can watch the live deploy log on screen.

> Note: Render's free tier sleeps after ~15 minutes idle, and waking up can take 30–90+ seconds. The project's `.github/workflows/keep-alive.yml` automatically pings `/status` every 10 minutes to prevent sleep — no extra setup needed, it takes effect automatically once the repo is pushed and GitHub Actions is enabled.

### 3. Test After Deployment Completes

Render will give you a URL that looks like:
```
https://fireless-war-backend.onrender.com
```

Open in your browser:
```
https://fireless-war-backend.onrender.com/status
```

Seeing `{"status": "ok", ...}` means the basic deployment succeeded.

---

## Part C. Environment Variables Overview

| Variable | Required? | Description |
|---|---|---|
| `PERMITTED_USER` | **Required** | Comma-separated list of GM emails, e.g. `a@gmail.com,b@gmail.com`. Unset = empty list = nobody can log in — a deliberate safety default. |
| `APPS_SCRIPT_URL` | **Required** (only if using `POST /record`) | The URL you get after deploying the Apps Script Web App, ending in `/exec`. See Part D. |
| `APPS_SCRIPT_SECRET` | **Required** (same as above) | Must exactly match the `SECRET` constant in the Apps Script, used to reject requests that don't carry this shared secret. |
| `DRIVE_FOLDER_ID` | **Required** (same as above) | The Drive folder ID where session files live; used by `GET /record` lookups. |
| `CREDENTIALS_PATH` | Optional | Path to the Service Account key file, defaults to `credentials/service_account.json`. Used as a file path for local dev; on Render this is usually mounted via Render's Secret File feature instead. |
| `SPREADSHEET_ID` | Optional | The fallback test file used when no `spreadsheet_id` parameter is provided — only relevant for local dev/testing. |
| `GOOGLE_CLIENT_ID` | Optional | Google OAuth Client ID, used to verify the ID Token sent from the frontend. Not a secret — the code has a hardcoded default, so you usually don't need to override it. |

Remember to `export` these values before testing locally, e.g.:

```bash
export PERMITTED_USER="your-google-account-email@gmail.com"
export APPS_SCRIPT_URL="https://script.google.com/macros/s/AKfycb.../exec"
export APPS_SCRIPT_SECRET="your secret"
export DRIVE_FOLDER_ID="your folder ID"
```

---

## Part D. Testing APIs That Require Login (`/record`, `/round`)

Part A's `/status` has no auth and can be opened directly in a browser address bar; but `/record` and `/round` now both require a valid Google ID Token in the request's `Authorization` header, and a browser address bar can't attach a custom header — so they can't be tested the same way `/status` can.

Two ways to test locally:

1. **Go through the real frontend end-to-end (recommended)**: run `fireless-war-web` with a local static server, complete Google sign-in, and the frontend will automatically attach the correct token.
2. **Test manually with curl**: sign in via the frontend first to get a token (in browser devtools' Network tab, copy the `Authorization` header value from any successful request), then pass it to curl:

```bash
curl -H "Authorization: Bearer <the ID Token you copied>" \
  "http://127.0.0.1:5001/round?day=1st&type=Morning"
```

Without a token, or if the token's email isn't in the `PERMITTED_USER`, you'll get a `401`.

**Example `/round` response shape** (the actual structure when reading real game data):

```json
{
  "day": "1st",
  "type": "Morning",
  "round_label": "第一天財報",
  "oniwara_out": false,
  "mike_out": false,
  "kouno_single": false,
  "legal_business": 52,
  "illegal_business": 54,
  "broken_target": 30,
  "business_level": {
    "oniwara": {
      "organization": "鬼原一家",
      "general_business": 8, "finance": 3, "sex": 1, "drug": 0, "arms": 6,
      "owned_money": 54, "current_integral": 123
    }
  },
  "kiyoshiro_escape": false,
  "hot_business": null
}
```

(`business_level` actually has all five characters — `oniwara`/`mike`/`kinugawa`/`kouno`/`ph003` — only one is shown here as an example.)

If `day` or `type` is wrong (e.g. `day=8th`), you'll get a `400` error with a clear message telling you what the valid values are.

**`/record` usage**:

```
GET /record?datetime=2026_07_01_18_30
```
- `200`: found, returns `{"spreadsheet_id": "..."}`
- `404`: no such file (the frontend can use this to ask the user whether to create a new session)
- `400`: invalid `datetime` format (should be `YYYY_MM_DD_HH_MM`)

```
POST /record?datetime=2026_07_01_18_30
```
- `201`: created successfully, returns `{"spreadsheet_id": "..."}`
- `500`: creation failed (e.g. can't reach Apps Script, wrong secret, a Drive issue)
- `400`: invalid `datetime` format

Once you have a `spreadsheet_id`, every subsequent `/round` call needs to include it — the backend is stateless and doesn't remember "which session is current" on its own:

```
GET /round?day=1st&type=Morning&spreadsheet_id=abc123...
```

Without `spreadsheet_id`, it falls back to the `SPREADSHEET_ID` environment variable (the default test file for local dev).

---

## About the `gunicorn app:app` Command (supplementary, doesn't affect how you operate anything)

`app.py` is the simple way to start the server for local testing; production uses `gunicorn` instead (a more robust server that can handle multiple requests). `app:app` means "go into the `app.py` file and find the Flask object named `app` to start." You don't need to memorize this line — just copy the setting as-is.

