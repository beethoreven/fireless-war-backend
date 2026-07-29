"""
測試腳本:驗證 Service Account 能否成功讀取 Google Sheet。
跑成功之後,這支腳本的邏輯會被搬進 Flask API 裡,這裡先獨立測試,方便除錯。
"""

import gspread
from google.oauth2.service_account import Credentials

# ---- 設定區 ----
CREDENTIALS_PATH = "credentials/service_account.json"

# 從 Google Sheet 網址複製出來的檔案 ID
# 例如網址 https://docs.google.com/spreadsheets/d/1bM_n6NBJLkivm8rbKz8tEPTpHnVDgjuSb3Gi3y9pOp8/edit
# 中間 /d/ 和 /edit 之間那一長串,就是 SPREADSHEET_ID
SPREADSHEET_ID = "1bM_n6NBJLkivm8rbKz8tEPTpHnVDgjuSb3Gi3y9pOp8"

SHEET_NAME = "Original_Status"
CELL = "C4"

# ---- 授權 ----
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=SCOPES)
client = gspread.authorize(creds)

# ---- 讀取 ----
spreadsheet = client.open_by_key(SPREADSHEET_ID)
worksheet = spreadsheet.worksheet(SHEET_NAME)
value = worksheet.acell(CELL).value

print(f"成功讀取到 {SHEET_NAME}!{CELL} 的值:{value}")
