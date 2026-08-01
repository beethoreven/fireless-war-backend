# 願浮沉2 後端 — Stage 1 最小可行版本

目標:架一支 `/status` API,先確保 Render 部署流程跑得通,之後再逐步加上讀取 Google Sheet 的邏輯。

---

## Part A. 先在你的 Mac 上本機測試(確認程式本身沒問題)

### 1. 確認你有 Python

打開「終端機」(Terminal),輸入:

```bash
python3 --version
```

如果有顯示版本號(例如 `Python 3.11.x`),代表你已經有 Python,可以跳到步驟2。
如果顯示「command not found」,先到 https://www.python.org/downloads/ 下載安裝。

### 2. 進入專案資料夾,建立「虛擬環境」

虛擬環境是什麼:簡單說,是幫這個專案獨立準備一個「乾淨房間」,裝的套件不會跟你電腦上其他 Python 專案打架。

```bash
cd 你解壓縮後的資料夾路徑/fireless-war-backend
python3 -m venv venv
source venv/bin/activate
```

執行完 `source venv/bin/activate` 後,你會看到終端機提示字元前面多了 `(venv)`,代表虛擬環境啟動成功。

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

> 註:這裡故意不用 5000,是因為 macOS 的 AirPlay 接收器功能常常佔用 5000 port,改用 5001 可以避開衝突,不需要去系統設定關閉 AirPlay。

### 5. 測試 API(開另一個終端機分頁,或直接用瀏覽器)

瀏覽器打開:`http://127.0.0.1:5001/status`

應該會看到:
```json
{"status": "ok", "message": "Fireless War backend is running"}
```

看到這個,代表程式本身沒問題,可以進入 Part B 部署到 Render。

按 `Control + C` 可以停止本機伺服器。

---

## Part B. 部署到 Render(讓這支 API 有一個網址,任何人都能連到)

### 1. 把專案傳到 GitHub(Render 需要從 GitHub 讀取程式碼來部署)

如果你還沒有這個專案的 GitHub repo:

```bash
git init
git add .
git commit -m "Stage 1: minimal status endpoint"
```

接著到 https://github.com/new 建立一個新的 repository(建議設為 Private,因為未來可能會放 Service Account 相關設定),建立好之後,GitHub 會顯示指令,大致像這樣(依你畫面顯示的為準):

```bash
git remote add origin https://github.com/你的帳號/fireless-war-backend.git
git branch -M main
git push -u origin main
```

### 2. 到 Render 建立 Web Service

1. 到 https://render.com 註冊/登入(可以直接用 GitHub 帳號登入,比較快)
2. 點右上角 **New +** → **Web Service**
3. 選擇「Connect a repository」,授權 Render 存取你的 GitHub,選擇剛剛建立的 `fireless-war-backend`
4. 填寫設定:
   - **Name**:自訂,例如 `fireless-war-backend`
   - **Region**:選 Singapore(離台灣最近,之後接資料庫也建議選同區域)
   - **Branch**:`main`
   - **Runtime**:Python 3
   - **Build Command**:`pip install -r requirements.txt`
   - **Start Command**:`gunicorn app:app --bind 0.0.0.0:$PORT`
     （Render 會用環境變數 `$PORT` 指定實際要用的 port,這行指令是告訴 gunicorn 要監聽那個 port,不能省略,不然部署後連不進去）
   - **Instance Type**:選 **Free**
5. 點 **Create Web Service**

Render 會開始自動建置,這個過程約 1~3 分鐘,你可以在畫面上看到即時的部署 log。

### 3. 部署完成後測試

Render 會給你一個網址,長得像:
```
https://fireless-war-backend.onrender.com
```

瀏覽器打開:
```
https://fireless-war-backend.onrender.com/status
```

看到 `{"status": "ok", ...}` 就代表 Stage 1 的最小目標達成了 🎉

---

## Part C. 測試新的 `/round` API(讀取回合資料)

本機啟動伺服器後(`python3 app.py`),瀏覽器打開:

```
http://127.0.0.1:5001/round?day=1st&type=Morning
```

會回傳 `1stDayMorning` 頁籤 A3:J8 的資料,格式類似:

```json
{
  "day": "1st",
  "type": "morning",
  "data": [
    {"角色": "鬼原響介", "代表組織": "鬼原一家", "正當事業": "6", ...}
  ]
}
```

如果 `day` 或 `type` 打錯(例如 `day=8th`),會回傳 400 錯誤,並附上清楚的錯誤訊息告訴你合法值有哪些。

> 注意:目前 `configs/config.py` 裡的 `SPREADSHEET_ID` 還是指向範例測試檔案,不是正式檔案,所以這裡讀到的資料是範例檔案裡 `1stDayMorning` 頁籤的內容(如果那個頁籤還沒建立或是空的,會回傳錯誤,這是正常的,先確認 API 邏輯本身沒問題即可)。

---

## Part D. 場次檔案的建立與查詢:`/record`

`/round` 讀的是「某一場遊戲」的 Sheet,但每場遊戲要先有一份對應的 Sheet 檔案才能讀。`/record` 就是負責「這場遊戲的檔案在哪」這件事:主持人輸入日期時間,`GET /record` 查有沒有現成的檔案,沒有的話再打 `POST /record` 建立一份新的(複製自 Template)。

### 為什麼建立檔案這個動作要繞一圈用 Apps Script

一開始的想法是後端直接呼叫 Google Drive API 複製 Template,但實際測試後發現兩條路都走不通:

- 用讀寫 `cloud_utils/sheet_access.py` 那組 **Service Account** 身分直接複製,會報 `storageQuotaExceeded`——Service Account 沒有自己的 Drive 儲存額度,無法擁有新建立的檔案,這是 Google 對這種身分類型的結構性限制,不是權限設定能調的。
- 改用 **OAuth(代表真人帳號)+ Google Picker** 這條路,理論上能繞開額度問題,但實測下來,Picker 選取既有檔案後的授權登記一直沒有生效(`files.get` 對已選取的檔案持續回 404),原因不明,排查多輪後放棄。

最後採用的方案:寫一支 **Apps Script**,部署成 Web App,讓 Flask 用 HTTP 請求呼叫它。Apps Script 執行時用的是你自己 Google 帳號的完整權限,不受上述兩個限制影響,`DriveApp.makeCopy()` 是 Google 原生的複製動作,公式、格式都完整保留。

程式碼在 `apps_script/Code.gs`,**這支不是 Python 檔案,不會被這個專案的 `pip install` 或 Render 部署動到**,需要另外手動部署到 Google 那邊,步驟見檔案開頭的註解。

### 環境變數

除了 Part B 提過的 `CREDENTIALS_PATH`(或 Render 上對應的 Secret File),還需要:

| 變數名稱 | 說明 |
|---|---|
| `APPS_SCRIPT_URL` | 部署 `apps_script/Code.gs` 後拿到的網址,結尾是 `/exec` |
| `APPS_SCRIPT_SECRET` | 跟 `Code.gs` 裡 `SECRET` 常數完全一致的密語,用來擋掉沒有這組密語的請求(因為 Apps Script Web App 設定成「知道連結的任何人」都能存取) |
| `DRIVE_FOLDER_ID` | 場次檔案所在的 Drive 資料夾 ID,`GET /record` 查詢時會用到 |

本機測試前記得先 `export` 這三個值,例如:

```bash
export APPS_SCRIPT_URL="https://script.google.com/macros/s/AKfycb.../exec"
export APPS_SCRIPT_SECRET="你的密語"
export DRIVE_FOLDER_ID="你的資料夾ID"
```

### API 用法

**查詢場次檔案**(純查詢,不會建立任何東西):

```
GET /record?datetime=2026_07_01_18_30
```

- `200`:找到,回傳 `{"spreadsheet_id": "..."}`
- `404`:查無此檔案(前端可據此詢問使用者是否要建立新場次)
- `400`:`datetime` 格式不合法(應為 `YYYY_MM_DD_HH_MM`)

**建立場次檔案**(複製 Template):

```
POST /record?datetime=2026_07_01_18_30
```

- `201`:建立成功,回傳 `{"spreadsheet_id": "..."}`
- `500`:建立失敗(例如 Apps Script 連不上、密語不對、Drive 發生問題)
- `400`:`datetime` 格式不合法

**串接 `/round`**:拿到 `spreadsheet_id` 後,之後每次呼叫 `/round` 都要附帶這個參數,後端是無狀態設計,不會自己記住「目前是哪一場」:

```
GET /round?day=1st&type=Morning&spreadsheet_id=abc123...
```

不帶 `spreadsheet_id` 時,會 fallback 用 `config.SPREADSHEET_ID`(本機測試用的預設檔案)。

---

## 關於 `gunicorn app:app` 這個指令(補充,不影響操作)

`app.py` 是本機測試用的簡易啟動方式,正式上線環境會用 `gunicorn`(一個更穩定、能處理多個請求的伺服器程式)。`app:app` 的意思是「去 `app.py` 這個檔案裡,找一個叫做 `app` 的 Flask 物件來啟動」。這行你不用背,照抄設定即可。
