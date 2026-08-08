"""
底層 Google Sheet 存取層。

這一層只負責「怎麼跟 Google Sheets API 對話」,完全不理解資料的業務意義
(不知道什麼是「正當事業」、不知道 1stDayMorning 代表第一天早晨)。
所有跟「資料代表什麼意義」有關的邏輯,都放在 parse_data.py,不要寫在這裡。
"""

import gspread
from google.oauth2.service_account import Credentials

from configs import config

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


def sheet_batch_read(ranges: list, spreadsheet_id: str = None):
    """
    一次讀取多個範圍(可以跨不同頁籤),只打一次 Google Sheets API。

    Google Sheets API 的配額是「每個 Service Account 身份每分鐘 60 次讀取」,
    逐格/逐範圍分開呼叫(例如 8 個小範圍分開讀 8 次)會不必要地快速吃掉這個配額。
    需要同時讀好幾個範圍時,一律應該用這支合併成一次呼叫。

    ranges: A1 表示法字串列表,可以加頁籤名稱前綴,
            例如 ["'1stDayMorning'!A1", "Global_Param!B3"]
    回傳:   對應每個 range 的二維陣列(values),順序跟輸入的 ranges 一致;
            該範圍完全沒有資料時,對應位置回傳空 list。
    """
    spreadsheet = _get_spreadsheet(spreadsheet_id)
    result = spreadsheet.values_batch_get(ranges)
    return [value_range.get("values", []) for value_range in result.get("valueRanges", [])]


# 這一層目前只做讀取。之前這裡放了 sheet_write / sheet_clear 兩個
# 只會 raise NotImplementedError 的空殼函式,沒有任何地方呼叫,已經移除;
# 真的要加寫入功能時,除了實作函式本身,還有兩件事一定要一起處理:
#   1. config.SCOPES 目前是 .readonly,要換成不含 readonly 的完整 scope
#   2. 到 Google Sheet 的共用設定,把 Service Account 從「檢視者」改成「編輯者」
# 少做任何一項,寫入都會被 Google 擋下來。
