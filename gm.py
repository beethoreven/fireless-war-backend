"""
主持人白名單。

一份寫死在程式碼裡的 dict,key 是主持人的顯示名稱(方便之後除錯、
看 log 時辨識是誰),value 是對應的 Gmail 帳號(拿來做 API 存取
判斷,以及建立新場次檔案時,授權給哪個帳號編輯者權限)。

要開放給新的主持人使用,直接在下面加一行就好,不用改任何其他地方,
也不需要對方做任何設定或同意——commit、push 上去,Render 自動重新
部署後就生效。要收回權限就把該行刪掉。

這裡比對的 email 是 Google 登入驗證過的(見 auth.py),不是使用者
自己宣稱的字串——換句話說,能不能用完全由這份名單決定,不是知道
email 字串就能冒充。
"""

GM_LIST = {
    "阿舍老師": "beethoreven@gmail.com",
    "日本阿舍": "arthur1.shen.pega@gmail.com",
}


def is_valid_gm_email(email: str) -> bool:
    """檢查這個 email 是不是白名單裡的主持人。"""
    if not email:
        return False
    return email in GM_LIST.values()
