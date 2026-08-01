"""
集中管理專案設定值。
本機開發時,直接讀寫死的值即可;
部署到 Render 之後,CREDENTIALS_PATH 相關的邏輯會改成從環境變數讀取
(因為 credentials/service_account.json 不會被推上 GitHub,Render 上不存在這個檔案路徑)。
這裡先讓本機開發能動,等接到 Render 那步,只需要改這個檔案,
不用去 sheet_access.py 或 parse_data.py 裡到處找字串。
"""

import os

# Google Sheet 檔案 ID(從 Sheet 網址 /d/ 和 /edit 中間那一串複製出來)
# 這組是本機測試/開發用的預設值(/round 沒帶 spreadsheet_id 參數時的 fallback)。
# 正式流程中,spreadsheet_id 會由 /record 找到或建立後,由前端在呼叫 /round 時帶入。
SPREADSHEET_ID = os.environ.get(
    "SPREADSHEET_ID",
    "1bM_n6NBJLkivm8rbKz8tEPTpHnVDgjuSb3Gi3y9pOp8",  # 目前先寫死範例檔案,之後改成正式檔案
)

# Service Account 金鑰檔案路徑(本機用,唯讀存取 Sheet/Drive)
CREDENTIALS_PATH = os.environ.get("CREDENTIALS_PATH", "credentials/service_account.json")

# Google API 權限範圍(Service Account 用)
# 唯讀就夠了:Sheet 內容讀取、Drive 檔案查詢都不需要寫入權限。
# 「建立新檔案」這個寫入動作,已經改由 Apps Script(見 apps_script/Code.gs)
# 用你自己的 Google 帳號身分執行,不經過 Service Account,
# 所以這裡刻意維持最小權限,不開放 Service Account 的寫入 scope。
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

# 合法的回合參數(用於 API 輸入驗證)
VALID_DAYS = ["1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "Final"]
VALID_TYPES = ["Morning", "Report"]

# Final 這個回合沒有 Morning,只有 Report(遊戲結束後的最終結算)
DAYS_WITHOUT_MORNING = ["Final"]

# ---- 以下為 Apps Script 相關設定,用於「複製 Template 建立新場次檔案」這個寫入動作 ----
# 部署 apps_script/Code.gs 成 Web App 之後拿到的網址(結尾是 /exec)。
# APPS_SCRIPT_SECRET 要跟 Code.gs 裡 SECRET 這個常數完全一致,
# 這組密語是因為 Apps Script Web App 設成「知道連結的任何人」都能存取,
# 用來擋掉沒有這組密語的請求,不是 Google 官方的驗證機制,是我們自己加的。
# 本機測試時用環境變數 export 設定,正式環境存在 Render 的環境變數裡,
# 絕對不要寫進程式碼或存進版本控制。
APPS_SCRIPT_URL = os.environ.get("APPS_SCRIPT_URL")
APPS_SCRIPT_SECRET = os.environ.get("APPS_SCRIPT_SECRET")

# 場次檔名格式驗證用(對應 FirelessWar_YYYY_MM_DD_HH_MM 命名規則)
RECORD_FILENAME_PREFIX = "FirelessWar_"

# 場次檔案所在的 Drive 資料夾 ID(給 drive_access.find_file_by_name 搜尋用)
DRIVE_FOLDER_ID = os.environ.get("DRIVE_FOLDER_ID")

# ---- Google 登入(Google Identity Services)用的 OAuth Client ID ----
# 這不是密鑰,是設計上就要公開嵌在前端頁面裡的識別碼,不用怕外流,
# 所以直接寫死當預設值也沒關係(跟 SPREADSHEET_ID 一樣可以用環境變數覆蓋)。
# 用途:驗證前端傳來的 Google ID Token 時,確認 token 的 audience
# 真的是我們自己這個 OAuth 用戶端,不是別人專案發出來的 token。
GOOGLE_CLIENT_ID = os.environ.get(
    "GOOGLE_CLIENT_ID",
    "665970888301-g3mjmlrba8aosq5j8jlkgqbukmp3u76p.apps.googleusercontent.com",
)
