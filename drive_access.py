"""
底層「檔案層級」Drive 存取層。

跟 sheet_access.py 的分工原則:
  sheet_access.py 負責「Sheet 內容層級」的操作(讀哪個儲存格、讀哪個範圍);
  這裡負責「檔案層級」的操作(找不找得到某個檔案、建立新檔案)。
  之後如果要判斷某個 Drive 操作該放在哪一層,先問「這是在操作檔案本身,
  還是檔案裡面的內容」,答案就是分工的依據。

查詢 vs 建立,底層走的是兩條完全不同的路,原因記錄如下:

  查詢(find_file_by_name):直接用 Service Account 的憑證打 Drive API,
  不透過 gspread(gspread 是給「Sheet 內容」操作用的,不適合拿來做檔案
  層級的查詢)。Service Account 對 Template 跟資料夾本來就有唯讀權限,
  查詢只是讀取,不會建立任何東西,不會撞到下面提到的儲存額度限制。

  建立(create_via_apps_script):改用 Apps Script Web App(見專案裡
  apps_script/Code.gs)。原因是 Service Account 沒有自己的 Drive
  儲存額度,無法「擁有」新建立的檔案,實測會直接報 storageQuotaExceeded,
  這是 Google 對 Service Account 這種身分類型的結構性限制,不是權限
  設定能調整的。必須借用一個有 Drive 儲存額度的身分去執行複製動作,
  Apps Script 正是用你自己的 Google 帳號身分執行的,所以能成功。

  （這條路之前也試過用 OAuth 憑證直接呼叫 Drive REST API,但透過
  Google Picker 選取既有檔案的授權登記一直沒有生效,實測連 files.get
  都讀不到,原因不明、且無法在這裡進一步排查,所以放棄那條路,
  改用現在這個 Apps Script 方案。）
"""

import requests
from google.auth.transport.requests import AuthorizedSession

import config
import sheet_access

DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"

# 模組層級的連線快取,避免每次呼叫都重新建立 session
_session = None


def _get_session():
    """取得(必要時建立)用 Service Account 憑證授權的 requests session。"""
    global _session

    if _session is None:
        _session = AuthorizedSession(sheet_access._get_credentials())

    return _session


def find_file_by_name(name: str, folder_id: str):
    """
    在指定資料夾中依檔名搜尋檔案(排除已丟進垃圾桶的)。
    找到回傳第一筆的 file_id,找不到回傳 None。

    name:      要找的檔名,例如 "FirelessWar_2026_07_01_18_30"
    folder_id: 資料夾 ID(對應 config.DRIVE_FOLDER_ID)
    """
    session = _get_session()
    query = f"name = '{name}' and '{folder_id}' in parents and trashed = false"

    resp = session.get(
        f"{DRIVE_API_BASE}/files",
        params={"q": query, "fields": "files(id, name)"},
    )
    resp.raise_for_status()

    files = resp.json().get("files", [])
    return files[0]["id"] if files else None


def create_via_apps_script(datetime_str: str):
    """
    呼叫 Apps Script Web App,用你自己的 Google 帳號身分複製 Template,
    建立新的場次檔案,回傳新檔案的 spreadsheet_id。

    datetime_str: 場次的日期時間字串(YYYY_MM_DD_HH_MM),檔名怎麼組、
                  要複製哪個 Template、放進哪個資料夾,這些細節都由
                  Apps Script 那邊自己決定(見 apps_script/Code.gs),
                  這裡只負責傳 datetime 過去、解讀回應。

    兩個平台特性要注意:
      1. Apps Script 的 doPost() 沒辦法自訂真正的 HTTP 狀態碼
         (ContentService 這個機制固定回 200),所以這裡看的是回應
         JSON 裡的 statusCode 欄位,不是 requests 拿到的 status_code。
      2. Apps Script 執行完會用 302 轉址到暫存結果頁面。requests 預設
         會自動跟隨轉址,且原本的 POST 會依照慣例自動降級成 GET 去抓
         最終結果(跟 curl 不手動指定 -X 時的行為一致),不需要額外處理。
    """
    resp = requests.post(
        config.APPS_SCRIPT_URL,
        json={"secret": config.APPS_SCRIPT_SECRET, "datetime": datetime_str},
        timeout=30,
    )
    resp.raise_for_status()  # 這裡只確認有沒有連線成功,不代表業務邏輯成功
    body = resp.json()

    if body.get("statusCode") != 200:
        raise RuntimeError(body.get("error", "Apps Script 回傳未知錯誤"))

    return body["spreadsheet_id"]
