"""
主持人白名單。

從 config.GM_WHITELIST_RAW 讀取(實際來源是 GM_WHITELIST 環境變數,
逗號分隔的 email 清單)——不是寫死在程式碼裡,這樣白名單本身就不會
進版本控制、不會因為 repo 是 Public 就被任何人看到。

要開放給新的主持人使用,不用改程式碼、不用 push:本機測試改用
export 設定環境變數,正式環境去 Render 後台(Dashboard → 這個服務
→ Environment)編輯 GM_WHITELIST 這個變數,存檔後 Render 會自動
重新部署套用新值。要收回權限,把對應的 email 從清單裡拿掉即可。

這裡比對的 email 是 Google 登入驗證過的(見 auth.py),不是使用者
自己宣稱的字串——換句話說,能不能用完全由這份名單決定,不是知道
email 字串就能冒充。
"""

import config

GM_LIST = {email.strip() for email in config.GM_WHITELIST_RAW.split(",") if email.strip()}


def is_valid_gm_email(email: str) -> bool:
    """檢查這個 email 是不是白名單裡的主持人。"""
    if not email:
        return False
    return email in GM_LIST
