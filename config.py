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
SPREADSHEET_ID = os.environ.get(
    "SPREADSHEET_ID",
    "1bM_n6NBJLkivm8rbKz8tEPTpHnVDgjuSb3Gi3y9pOp8",  # 目前先寫死範例檔案,之後改成正式檔案
)

# Service Account 金鑰檔案路徑(本機用)
CREDENTIALS_PATH = os.environ.get("CREDENTIALS_PATH", "credentials/service_account.json")

# Google API 權限範圍
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

# 合法的回合參數(用於 API 輸入驗證)
VALID_DAYS = ["1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "Final"]
VALID_TYPES = ["Morning", "Report"]

# Final 這個回合沒有 Morning,只有 Report(遊戲結束後的最終結算)
DAYS_WITHOUT_MORNING = ["Final"]
