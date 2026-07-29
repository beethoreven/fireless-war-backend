"""
底層 Google Sheet 存取層。

這一層只負責「怎麼跟 Google Sheets API 對話」,完全不理解資料的業務意義
(不知道什麼是「正當事業」、不知道 1stDayMorning 代表第一天早晨)。
所有跟「資料代表什麼意義」有關的邏輯,都放在 parse_data.py,不要寫在這裡。
"""

import gspread
from google.oauth2.service_account import Credentials

import config

# 模組層級的連線快取,避免每次呼叫都重新驗證一次(驗證有網路成本,也可能踩到 API 頻率限制)
_client = None
_spreadsheet = None


def _get_spreadsheet():
    """取得(必要時建立)Google Sheet 連線,重複呼叫會重用同一個連線。"""
    global _client, _spreadsheet

    if _spreadsheet is None:
        creds = Credentials.from_service_account_file(
            config.CREDENTIALS_PATH, scopes=config.SCOPES
        )
        _client = gspread.authorize(creds)
        _spreadsheet = _client.open_by_key(config.SPREADSHEET_ID)

    return _spreadsheet


def sheet_read(sheet_name: str, cell: str):
    """
    讀取指定頁籤中,單一儲存格的值。

    sheet_name: 頁籤名稱,例如 "Original_Status"
    cell:       A1 表示法的儲存格座標,例如 "C4"
    """
    spreadsheet = _get_spreadsheet()
    worksheet = spreadsheet.worksheet(sheet_name)
    return worksheet.acell(cell).value


def sheet_matrix_read(sheet_name: str, start_col: str, end_col: str, start_row: int, end_row: int):
    """
    讀取指定頁籤中,一個矩形範圍的值,回傳二維陣列(list of list)。

    sheet_name:         頁籤名稱,例如 "1stDayMorning"
    start_col, end_col: 欄位字母,例如 "A", "J"
    start_row, end_row: 列號(整數),例如 3, 8

    範例:sheet_matrix_read("1stDayMorning", "A", "J", 3, 8)
         會讀取 A3:J8 這個範圍,回傳 6 列、每列最多 10 欄的資料
    """
    spreadsheet = _get_spreadsheet()
    worksheet = spreadsheet.worksheet(sheet_name)

    a1_range = f"{start_col}{start_row}:{end_col}{end_row}"
    return worksheet.get(a1_range)


def sheet_write(sheet_name: str, cell: str, value):
    """
    寫入指定儲存格(尚未實作)。
    未來若開放寫入功能,記得同步：
      1. 把 config.SCOPES 加上 spreadsheets 的寫入權限
         (目前是 .readonly,寫入需要改成不含 readonly 的完整 scope)
      2. 到 Google Sheet 的共用設定,把 Service Account 的權限從「檢視者」改成「編輯者」
    """
    raise NotImplementedError("寫入功能尚未實作")


def sheet_clear(sheet_name: str, cell_range: str):
    """
    清空指定範圍的內容(尚未實作)。
    注意事項同 sheet_write。
    """
    raise NotImplementedError("清空功能尚未實作")
