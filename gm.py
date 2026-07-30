"""
主持人白名單。

目前用最簡單的方式管理:一份寫死在程式碼裡的 dict,
key 是主持人的顯示名稱(方便之後除錯、看 log 時辨識是誰),
value 是對應的 Gmail 帳號(拿來做 API 存取判斷,以及建立新場次
檔案時,授權給哪個帳號編輯者權限)。

這不是真正的身分驗證——沒有登入機制,任何人只要知道有效的 email
字串,就能在 API 呼叫時冒用。只能擋掉「完全不知道任何有效 email」
的隨機亂打或掃描,擋不住主持人之間互相冒用彼此 email 這種情況。
如果之後需要更嚴謹的保護,要換成真正的 Google 登入(Google
Identity Services 前端登入 + 後端驗證 ID Token),那樣 email
會由 Google 簽章保證真實性,無法被冒用,是完全不同、更可靠的機制。
目前先用這個最簡單的版本起步,之後要換不會動到呼叫端的介面設計
(一樣是「帶一個 email 過來」),只是後端驗證方式會不一樣。
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
