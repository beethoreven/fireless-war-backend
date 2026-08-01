"""
業務邏輯層。

這一層知道「Google Sheet 裡的資料代表什麼意義」:
知道 1stDayMorning 是第一天早晨、知道 A~J 欄分別是什麼欄位。
只呼叫 sheet_access.py 提供的底層函式,不直接碰 gspread。
"""

from configs import config
from cloud_utils import sheet_access

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

# Sheet 上的角色姓名 -> 前端 API 用的英文 key
# 這個對照表是固定的,不受 oniwara_out/mike_out/kouno_single 轉換影響
# (轉換只改「代表組織」「事業名稱/顏色」這些顯示層的東西,英文 key 本身不變)
CHARACTER_SLUGS = {
    "鬼原響介": "oniwara",
    "麥克・葛雷希爾": "mike",
    "鬼怒川新助": "kinugawa",
    "河野麗一": "kouno",
    "PH-003": "ph003",
}

# 五個事業欄位的中文名稱 -> 前端 API 用的英文 key
# 同樣固定不變,即使顯示名稱因為 oniwara_out 轉換變成「金融/餐酒/藥妝」,這裡的 key 還是原本這套
BUSINESS_KEY_MAP = {
    "正當事業": "general_business",
    "闇金": "finance",
    "色情": "sex",
    "毒品": "drug",
    "軍火": "arms",
}

# 非法事業的四個類別(不含正當事業),oniwara_out 觸發時鬼原響介這四項會被排除在外
ILLEGAL_BUSINESS_KEYS = ["finance", "sex", "drug", "arms"]

# 「風頭事業」平手時的優先序(由前到後優先):毒品 > 金融(闇金)> 軍火 > 色情
HOT_BUSINESS_PRIORITY = ["drug", "finance", "arms", "sex"]

GLOBAL_PARAM_SHEET = "Global_Param"
ORIGINAL_STATUS_SHEET = "OriginalStatus"


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


def _to_int(value):
    """儲存格數字欄位轉成 int,空字串視為 0。"""
    if value in ("", None):
        return 0
    return int(value)


def _cell_value(batch_values, idx, default=""):
    """從 sheet_batch_read 的結果裡取出第 idx 個 range 的單一儲存格值,取不到就回傳 default。"""
    rows = batch_values[idx]
    if rows and rows[0]:
        return rows[0][0]
    return default


def _read_round_batch(sheet_name: str, spreadsheet_id):
    """
    一次讀完組一份 /round 回應需要的所有原始資料(只打一次 Google Sheets API):
    這個回合頁籤的 A1 標題 + A4:J8 角色資料表,
    以及 Global_Param 三個全域轉換開關、OriginalStatus 三個事業基數/崩壞指數。

    這幾個值在遊戲過程中隨時可能被主持人手動改動,所以每次呼叫都重新讀,不快取;
    但改成一次 batch 呼叫,不代表可以接受快取——只是把「重新讀」的配額成本從 8 次降到 1 次。
    """
    ranges = [
        f"'{sheet_name}'!A1",
        f"'{sheet_name}'!A4:J8",
        f"{GLOBAL_PARAM_SHEET}!B3",
        f"{GLOBAL_PARAM_SHEET}!B4",
        f"{GLOBAL_PARAM_SHEET}!B5",
        f"{ORIGINAL_STATUS_SHEET}!M3",
        f"{ORIGINAL_STATUS_SHEET}!M4",
        f"{ORIGINAL_STATUS_SHEET}!M5",
        f"{GLOBAL_PARAM_SHEET}!B10",
    ]
    batch = sheet_access.sheet_batch_read(ranges, spreadsheet_id)

    return {
        "round_label": _cell_value(batch, 0),
        "rows": batch[1],
        "oniwara_out": _cell_value(batch, 2) == "是",
        "mike_out": _cell_value(batch, 3) == "是",
        "kouno_single": _cell_value(batch, 4) == "是",
        "legal_basic": _to_int(_cell_value(batch, 5, "0")),
        "illegal_basic": _to_int(_cell_value(batch, 6, "0")),
        "broken_target": _to_int(_cell_value(batch, 7, "0")),
        "kiyoshiro_escape": _cell_value(batch, 8) == "是",
    }


def _rows_to_business_level(rows, format_fields, is_report_format: bool, kouno_single: bool):
    """
    把 A4:J8 讀到的原始列資料,轉換成前端要的英文 key 格式。

    河野麗一併入 PH-003 的積分合併規則在這裡處理:kouno_single=False 時,
    河野麗一當次的積分(current_integral 或 expected_integral,視 type 而定)設為 None,
    同一筆數字併加到 PH-003 對應欄位上;金錢欄位不受影響,永遠是本人真實數字。
    """
    business_level = {}
    for row in rows:
        char_name = row[0] if row else ""
        slug = CHARACTER_SLUGS.get(char_name)
        if slug is None:
            continue

        entry = {"organization": row[1] if len(row) > 1 else ""}
        for idx, field_name in enumerate(format_fields):
            if field_name is None or idx in (0, 1):
                continue
            value = row[idx] if idx < len(row) else ""
            if field_name in BUSINESS_KEY_MAP:
                entry[BUSINESS_KEY_MAP[field_name]] = _to_int(value)
            elif field_name == "持有金錢":
                entry["owned_money"] = _to_int(value)
            elif field_name == "當前積分":
                entry["current_integral"] = _to_int(value)
            elif field_name == "應得收入":
                entry["expected_income"] = _to_int(value)
            elif field_name == "應持金錢":
                entry["expected_money"] = _to_int(value)
            elif field_name == "預期積分":
                entry["expected_integral"] = _to_int(value)

        business_level[slug] = entry

    integral_field = "expected_integral" if is_report_format else "current_integral"
    if not kouno_single and "kouno" in business_level and "ph003" in business_level:
        kouno_value = business_level["kouno"].get(integral_field, 0)
        business_level["ph003"][integral_field] = (
            business_level["ph003"].get(integral_field, 0) + kouno_value
        )
        business_level["kouno"][integral_field] = None

    return business_level


def _compute_business_totals(business_level, oniwara_out: bool, legal_basic: int, illegal_basic: int):
    """
    計算合法事業/非法事業總和。
    預設每個角色的正當事業算合法、其餘四項算非法;
    oniwara_out=True 時,鬼原商事(鬼原響介)整個洗白,五項事業全部改算合法。
    """
    legal_total = legal_basic
    illegal_total = illegal_basic

    for slug, entry in business_level.items():
        if slug == "oniwara" and oniwara_out:
            legal_total += entry["general_business"]
            for key in ILLEGAL_BUSINESS_KEYS:
                legal_total += entry[key]
        else:
            legal_total += entry["general_business"]
            for key in ILLEGAL_BUSINESS_KEYS:
                illegal_total += entry[key]

    return legal_total, illegal_total


def _compute_hot_business(business_level, oniwara_out: bool):
    """
    計算「風頭事業」:加總所有角色四項非法事業的等級(oniwara_out=True 時排除鬼原響介,
    因為鬼原商事已經洗白,不再算非法),取加總數字最高的類別;
    同分時依 HOT_BUSINESS_PRIORITY(毒品>金融>軍火>色情)決定顯示哪一個。
    """
    totals = {key: 0 for key in ILLEGAL_BUSINESS_KEYS}
    for slug, entry in business_level.items():
        if slug == "oniwara" and oniwara_out:
            continue
        for key in ILLEGAL_BUSINESS_KEYS:
            totals[key] += entry[key]

    max_value = max(totals.values())
    for key in HOT_BUSINESS_PRIORITY:
        if totals[key] == max_value:
            return key
    return None


def build_round_response(day: str, type: str, spreadsheet_id: str = None):
    """
    組出 /round API 的完整回應內容。

    spreadsheet_id: 要讀哪一場遊戲的 Sheet(通常來自 GET /record 回傳的值)。
                    不傳則 fallback 用 config.SPREADSHEET_ID(本機測試用)。

    day="Final" 時(只能配 type="Report"),讀取的是 FinalDayResult 頁籤,
    欄位結構跟 Morning 型態相同(H欄空白),不是一般 Report 頁籤的結構。
    """
    day, type = validate_round_params(day, type)
    sheet_name = _resolve_sheet_name(day, type)
    format_fields = _resolve_format(day, type)
    is_report_format = format_fields is REPORT_FORMAT

    batch = _read_round_batch(sheet_name, spreadsheet_id)

    business_level = _rows_to_business_level(
        batch["rows"], format_fields, is_report_format, batch["kouno_single"]
    )
    legal_business, illegal_business = _compute_business_totals(
        business_level, batch["oniwara_out"], batch["legal_basic"], batch["illegal_basic"]
    )
    hot_business = (
        _compute_hot_business(business_level, batch["oniwara_out"])
        if batch["kiyoshiro_escape"]
        else None
    )

    return {
        "day": day,
        "type": type,
        "round_label": batch["round_label"],
        "oniwara_out": batch["oniwara_out"],
        "mike_out": batch["mike_out"],
        "kouno_single": batch["kouno_single"],
        "legal_business": legal_business,
        "illegal_business": illegal_business,
        "broken_target": batch["broken_target"],
        "business_level": business_level,
        "kiyoshiro_escape": batch["kiyoshiro_escape"],
        "hot_business": hot_business,
    }
