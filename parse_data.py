"""
業務邏輯層。

這一層知道「Google Sheet 裡的資料代表什麼意義」:
知道 1stDayMorning 是第一天早晨、知道 A~J 欄分別是什麼欄位。
只呼叫 sheet_access.py 提供的底層函式,不直接碰 gspread。
"""

import config
import sheet_access

# 適用於「Morning 型態」頁籤的資料格式(1stDayMorning ~ 7thDayMorning,以及 FinalDayResult)
# 這幾種頁籤共通點:H欄是空白分隔欄,I=持有金錢,J=當前積分
# 注意:一般的 XthDayReport 頁籤資料格式不同(H欄是「應得收入」,不是空白),
#      不能套用這份定義,詳見 REPORT_FORMAT 的說明
MORNING_FORMAT = [
    "角色",
    "代表組織",
    "正當事業",
    "闇金",
    "色情",
    "毒品",
    "軍火",
    None,
    "持有金錢",
    "當前積分",
]

# 一般 Report 頁籤(1stDayReport ~ 7thDayReport)的資料格式
# 依交接文件描述:C~G=注資後新等級,H=應得收入,I=應持金錢,J=預期積分
# 已用 1stDayReport 實際資料驗證過(積分較 Morning 上升,符合注資後成長的預期)
# 注意:I/J 欄用字刻意跟 MORNING_FORMAT 不同——
#      Report 的「應持金錢」「預期積分」是估算值,語意上跟 Morning 的
#      「持有金錢」「當前積分」(已確定的當下數字)不一樣,不能混用同一套詞彙
REPORT_FORMAT = [
    "角色",
    "代表組織",
    "正當事業",
    "闇金",
    "色情",
    "毒品",
    "軍火",
    "應得收入",
    "應持金錢",
    "預期積分",
]


def validate_round_params(day: str, type: str):
    """
    驗證 day / type 參數是否合法,並回傳正規化後的值。
    day 例如 "1st"、"2nd";type 必須是 "Morning" 或 "Report"(首字大寫,大小寫需完全符合)。
    不合法時丟出 ValueError,讓 app.py 那層可以接住並回傳 400。
    """
    if day not in config.VALID_DAYS:
        raise ValueError(f"day 參數不合法:{day},合法值為 {config.VALID_DAYS}")

    # 自動正規化大小寫(不分 morning/Morning/MORNING),主要是為了避免瀏覽器網址列
    # 自動完成把大寫誤改成小寫時,誤導你以為是程式邏輯出錯
    normalized_type = type.capitalize()
    if normalized_type not in config.VALID_TYPES:
        raise ValueError(f"type 參數不合法:{type},合法值為 {config.VALID_TYPES}")

    if day in config.DAYS_WITHOUT_MORNING and normalized_type == "Morning":
        raise ValueError(f"{day} 沒有 Morning 回合,只有 Report")

    return day, normalized_type


def _resolve_sheet_name(day: str, type: str):
    """
    決定要去讀 Google Sheet 的哪個頁籤。
    大部分回合遵循 {day}Day{type} 規則(例如 1st + Morning -> "1stDayMorning");
    Final 是例外——頁籤名稱固定是 "FinalDayResult",不是 "FinalDayReport",
    這是刻意的命名區隔,避免跟一般 Report 頁籤的資料格式(有應得收入等計算欄位)搞混,
    因為 Final 的資料結構其實跟 Morning 型態一樣(H欄空白)。
    """
    if day in config.DAYS_WITHOUT_MORNING:
        return "FinalDayResult"
    return f"{day}Day{type}"


def _resolve_format(day: str, type: str):
    """
    決定這個頁籤該用哪一種資料格式(欄位定義)。
    Morning 型態的頁籤(含 FinalDayResult)用 MORNING_FORMAT;
    一般 Report 頁籤(1st~7th)用 REPORT_FORMAT。
    """
    if type == "Morning" or day in config.DAYS_WITHOUT_MORNING:
        return MORNING_FORMAT
    return REPORT_FORMAT


def parse_round_status(day: str, type: str, spreadsheet_id: str = None):
    """
    讀取指定回合頁籤的角色狀態表,回傳一個 list,每個元素是一位角色的資料字典。

    spreadsheet_id: 要讀哪一場遊戲的 Sheet(通常來自 GET /record 回傳的值)。
                    不傳則 fallback 用 config.SPREADSHEET_ID(本機測試用)。

    範例:parse_round_status("1st", "Morning", "abc123...")
         會去讀 spreadsheet_id 對應檔案的 "1stDayMorning" 頁籤 A4:J8,回傳類似:
         [
           {"角色": "鬼原響介", "代表組織": "鬼原一家", "正當事業": "8", ..., "當前積分": "123"},
           ...
         ]

    day="Final" 時(只能配 type="Report"),讀取的是 FinalDayResult 頁籤,
    欄位結構跟 Morning 型態相同(H欄空白),不是一般 Report 頁籤的結構。
    """
    day, type = validate_round_params(day, type)
    sheet_name = _resolve_sheet_name(day, type)
    format_fields = _resolve_format(day, type)

    rows = sheet_access.sheet_matrix_read(
        sheet_name, "A", "J", 4, 8, spreadsheet_id=spreadsheet_id
    )

    result = []
    for row in rows:
        entry = {}
        for idx, field_name in enumerate(format_fields):
            if field_name is None:
                continue
            # 保護:如果某列資料比預期短(例如末端空白被 Google API 省略),補空字串
            value = row[idx] if idx < len(row) else ""
            entry[field_name] = value
        result.append(entry)

    return result
