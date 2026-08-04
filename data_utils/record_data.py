"""
業務邏輯層,處理「場次檔案(record)」的意義。

跟 parse_data.py 屬於同一層級:知道檔名該怎麼組、找不到時該複製哪個 Template、
該放進哪個資料夾。只呼叫 drive_access.py 提供的底層函式,不直接碰 Drive API。

find_record / create_record 刻意拆成兩支獨立函式,對應 app.py 那邊
GET(只查)、POST(只建)兩支各自獨立的 API,職責單純不混在一起。
"""

import re

from configs import config
from cloud_utils import drive_access

# 場次檔名格式:FirelessWar_YYYY_MM_DD_HH_MM
# datetime 參數只需要傳 "YYYY_MM_DD_HH_MM" 這段,前綴由這裡統一補上
_DATETIME_PATTERN = re.compile(r"^\d{4}_\d{2}_\d{2}_\d{2}_\d{2}$")


def validate_datetime_param(datetime_str: str):
    """
    驗證 datetime 參數格式是否合法(YYYY_MM_DD_HH_MM)。
    不合法時丟出 ValueError,讓 app.py 那層接住並回傳 400。
    這裡只驗證格式,不驗證日期是否真實存在(例如 13 月、32 號),
    因為場次檔名只是拿來當唯一識別字串,不會被拿去做日期運算。
    """
    if not _DATETIME_PATTERN.match(datetime_str):
        raise ValueError(
            f"datetime 參數格式不正確:{datetime_str},應為 YYYY_MM_DD_HH_MM(例如 2026_07_01_18_30)"
        )
    return datetime_str


def _resolve_record_filename(datetime_str: str):
    """把 datetime 參數組成完整的場次檔名。"""
    return f"{config.RECORD_FILENAME_PREFIX}{datetime_str}"


DEMO_FILENAME = f"{config.RECORD_FILENAME_PREFIX}Demo"


def find_demo_record():
    """
    Demo 版本專用:直接查詢固定的 FirelessWar_Demo 場次檔案,不需要日期時間參數
    ——demo 永遠讀同一份固定的 Sheet(必須事先手動在 Drive 資料夾裡準備好,
    複製自同一個 Template,檔名精確是 "FirelessWar_Demo")。

    找到 -> 回傳 spreadsheet_id
    找不到 -> 回傳 None(由 app.py 那層決定要回 404)
    """
    return drive_access.find_file_by_name(DEMO_FILENAME, config.DRIVE_FOLDER_ID)


def find_record(datetime_str: str):
    """
    依日期時間字串搜尋既有的場次檔案。

    找到 -> 回傳 spreadsheet_id
    找不到 -> 回傳 None(由 app.py 那層決定要回 404)

    對應 GET /record,純查詢,不會建立任何東西。
    """
    datetime_str = validate_datetime_param(datetime_str)
    filename = _resolve_record_filename(datetime_str)
    return drive_access.find_file_by_name(filename, config.DRIVE_FOLDER_ID)


def create_record(datetime_str: str, editor_email: str = None):
    """
    請 Apps Script 複製 Template,建立新的場次檔案,並把 editor_email
    加為這份新檔案的編輯者,回傳 (spreadsheet_id, warning) tuple
    (warning 平常是 None,詳見 drive_access.create_via_apps_script 的說明)。

    對應 POST /record,只負責建立,不會先檢查是否已存在
    (是否該建立的判斷,由前端在收到 GET 的 404 之後自己決定要不要打這支)。

    檔名怎麼組、複製哪個 Template、放進哪個資料夾,這些細節現在都由
    Apps Script 那邊自己決定(見 apps_script/Code.gs),這裡只驗證參數格式、
    把 datetime 跟 editor_email 傳過去。Apps Script 走的是同步操作,
    這支函式回傳時,新檔案已經確定複製完成,回傳的 spreadsheet_id
    可以直接拿去用。

    editor_email 沒傳(None)時,Apps Script 那邊只會建立檔案,
    不會額外加編輯者。
    """
    datetime_str = validate_datetime_param(datetime_str)
    return drive_access.create_via_apps_script(datetime_str, editor_email)
