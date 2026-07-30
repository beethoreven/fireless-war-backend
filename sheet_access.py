"""
底層 Google Sheet 存取層。

這一層只負責「怎麼跟 Google Sheets API 對話」,完全不理解資料的業務意義
(不知道什麼是「正當事業」、不知道 1stDayMorning 代表第一天早晨)。
所有跟「資料代表什麼意義」有關的邏輯,都放在 parse_data.py,不要寫在這裡。
"""

import gspread
from google.oauth2.service_account import Credentials

import config

# 模組層級的連線快取。
# _credentials / _client 只需要建立一次(驗證有網路成本,也可能踩到 API 頻率限制)。
# _spreadsheet_cache 改成 dict,因為現在會讀取多份不同的 Sheet(每場遊戲一份),
# 用 spreadsheet_id 當 key 個別快取,避免每次都重新 open_by_key。
_credentials = None
_client = None
_spreadsheet_cache = {}


def _get_credentials():
    """
    取得(必要時建立)原始的 Service Account 憑證物件(未經 gspread 包裝)。
    drive_access.py 會直接拿這個憑證去打 Drive REST API 的檔案查詢,
    不透過 gspread,因為那是「檔案層級」操作,跟這裡「Sheet 內容層級」
    的職責不同,詳見 drive_access.py 開頭的說明。
    """
    global _credentials
    if _credentials is None:
        _credentials = Credentials.from_service_account_file(
            config.CREDENTIALS_PATH, scopes=config.SCOPES
        )
    return _credentials


def _get_client():
    """取得(必要時建立)Google API 用戶端,重複呼叫會重用同一個。"""
    global _client

    if _client is None:
        _client = gspread.authorize(_get_credentials())

    return _client


def _get_spreadsheet(spreadsheet_id: str = None):
    """
    取得(必要時開啟)指定的 Google Sheet 連線。
    spreadsheet_id 沒傳時,fallback 用 config.SPREADSHEET_ID(本機測試用的預設檔案)。
    """
    sid = spreadsheet_id or config.SPREADSHEET_ID

    if sid not in _spreadsheet_cache:
        client = _get_client()
        _spreadsheet_cache[sid] = client.open_by_key(sid)

    return _spreadsheet_cache[sid]


def sheet_read(sheet_name: str, cell: str, spreadsheet_id: str = None):
    """
    讀取指定頁籤中,單一儲存格的值。

    sheet_name:     頁籤名稱,例如 "Original_Status"
    cell:           A1 表示法的儲存格座標,例如 "C4"
    spreadsheet_id: 要讀哪一份 Sheet,不傳則用 config.SPREADSHEET_ID
    """
    spreadsheet = _get_spreadsheet(spreadsheet_id)
    worksheet = spreadsheet.worksheet(sheet_name)
    return worksheet.acell(cell).value


def sheet_matrix_read(
    sheet_name: str,
    start_col: str,
    end_col: str,
    start_row: int,
    end_row: int,
    spreadsheet_id: str = None,
):
    """
    讀取指定頁籤中,一個矩形範圍的值,回傳二維陣列(list of list)。

    sheet_name:         頁籤名稱,例如 "1stDayMorning"
    start_col, end_col: 欄位字母,例如 "A", "J"
    start_row, end_row: 列號(整數),例如 3, 8
    spreadsheet_id:     要讀哪一份 Sheet,不傳則用 config.SPREADSHEET_ID

    範例:sheet_matrix_read("1stDayMorning", "A", "J", 3, 8)
         會讀取 A3:J8 這個範圍,回傳 6 列、每列最多 10 欄的資料
    """
    spreadsheet = _get_spreadsheet(spreadsheet_id)
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
