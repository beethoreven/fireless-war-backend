"""
Google 登入驗證層。

負責驗證前端傳來的 Google ID Token——這不是 Service Account 憑證,
是主持人自己用 Google 帳號登入後,瀏覽器拿到的一段身分證明(JWT)。

驗證的三件事:
1. 這個 token 真的是 Google 簽發的(用 Google 的公開金鑰驗證簽章,
   google-auth 這個套件會自動處理金鑰快取/輪替,不用自己管)
2. 沒有過期
3. audience 對得上我們自己的 OAuth Client ID(不是別人專案的登入憑證)

驗證通過後,回傳 token payload 裡「Google 保證過的」email;
只要上面任何一項不通過,一律回傳 None,呼叫端自己決定要回什麼錯誤,
這一層不負責判斷這個 email 在不在白名單裡(那是 gm.py 的事)。
"""

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from configs import config

_google_request = google_requests.Request()


class VerificationUnavailable(Exception):
    """
    「這次驗不了」,不等於「這個 token 是假的」。

    驗證 ID Token 需要跟 Google 拿公開金鑰,連不上 Google、逾時、
    對方暫時掛掉,都會落在這一類。這種情況必須跟「token 真的無效」
    分開處理——混在一起的話,Google 那邊打個嗝就會把正在跑團的主持人
    誤判成登入過期踢出去,而他手上的 token 其實好好的。
    """


def verify_google_id_token(token: str):
    """
    驗證 Google ID Token,回傳驗證過的 email(字串)。

    token 確定無效(格式錯、簽章不符、過期、audience 不對)回傳 None;
    但如果是「暫時驗不了」(連不上 Google 等),丟出 VerificationUnavailable,
    讓呼叫端可以回一個「稍後再試」而不是「你沒登入」。
    """
    if not token:
        return None

    try:
        payload = id_token.verify_oauth2_token(
            token, _google_request, config.GOOGLE_CLIENT_ID
        )
    except ValueError:
        # 格式錯誤、簽章驗證失敗、過期、audience 不符,都會是 ValueError
        return None
    except Exception as e:
        # 其餘全部視為「這次驗不了」(TransportError、連線逾時等)。
        # 這裡刻意攔得寬:任何非 ValueError 的意外,都不該被解讀成
        # 「這個使用者的登入無效」,寧可回報成暫時性故障。
        raise VerificationUnavailable(str(e)) from e

    if not payload.get("email_verified"):
        # Google 帳號本身的 email 沒有經過驗證(理論上很少見),不能信任
        return None

    return payload.get("email")


def extract_bearer_token(request):
    """
    從 `Authorization: Bearer <token>` header 取出 token 字串;
    header 沒帶或格式不對,回傳 None。
    """
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    return header[len("Bearer "):].strip() or None
