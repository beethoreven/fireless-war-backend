"""
願浮沉2:無火戰爭 —— 後端 API
"""

from functools import wraps

from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_limiter import Limiter

from auth_utils import auth
from auth_utils import gm
from data_utils import parse_data
from data_utils import record_data

app = Flask(__name__)
app.json.ensure_ascii = False

# 前端(GitHub Pages)透過瀏覽器 fetch 呼叫這裡,需要 CORS 允許來源網域。
# 本機開發(任意 port 的 localhost/127.0.0.1)也一併放行方便測試。
# allow_headers 要明確帶 Authorization——登入後每次 API 呼叫都會帶
# `Authorization: Bearer <Google ID Token>`,沒有這行,瀏覽器的
# CORS 預檢(preflight)會擋下這個 header,請求根本送不到後端。
# 下面兩條 localhost 規則是 regex,而 Flask-CORS 比對 regex 時用的是 re.match——
# 只保證「開頭吻合」,不會自動比對到結尾。少了結尾的 $,像
# `http://localhost:8080.example.com` 這種前綴相同的來源也會被放行
# (實測確認過)。雖然瀏覽器的 Origin 不可能長這樣、而且這個 API 是用
# Authorization header 而不是 cookie 驗證(就算來源被放行也偷不到 token),
# 但補上 $ 是零成本的,不要把安全性建立在「瀏覽器應該不會這樣送」上面。
CORS(
    app,
    origins=[
        "https://beethoreven.github.io",
        r"http://localhost:\d+$",
        r"http://127\.0\.0\.1:\d+$",
    ],
    allow_headers=["Content-Type", "Authorization"],
)

# /round 每次呼叫會打 1 次 Google Sheets API(已用 batchGet 合併過)。
# Google 官方配額是「每個 Service Account 身份每分鐘 60 次讀取」,這個配額是
# 全站共用的(不分是哪個主持人、哪一場遊戲),所以這裡刻意做成全站共用一個額度,
# 不是分別限制每個 IP——保護的是共用的 Google 配額本身,不是防止單一使用者太活躍。
# 30/分鐘 = Google 上限的一半,留一半安全邊際,同時遠高於正常對戰使用量
# (一場 6 小時的遊戲預期打不到 20 次)。
limiter = Limiter(key_func=lambda: "global", app=app, storage_uri="memory://")


def require_gm_email(view_func):
    """
    裝飾器:檢查請求有沒有帶合法的 Google 登入憑證,且對應的 email 在白名單裡。

    從 `Authorization: Bearer <token>` header 讀取前端登入後拿到的
    Google ID Token,交給 auth.verify_google_id_token 驗證簽章/過期時間/
    audience,拿到「Google 保證過的」email,再比對 gm.py 的白名單。
    token 無效或 email 不在白名單,一律回 401,不會進到實際的路由邏輯。

    驗證通過後,把 email 存進 request.gm_email,下游路由需要時可以直接拿,
    不用再自己重新解一次 token。
    """

    @wraps(view_func)
    def wrapper(*args, **kwargs):
        token = auth.extract_bearer_token(request)
        try:
            email = auth.verify_google_id_token(token)
        except auth.VerificationUnavailable:
            # 連不上 Google 驗不了,不是這個使用者的問題——回 503 而不是 401,
            # 前端才不會把暫時性故障當成登入失效、把人踢出登入狀態。
            return jsonify({"error": "目前無法驗證登入狀態,請稍後再試"}), 503
        if email is None or not gm.is_valid_gm_email(email):
            return jsonify({"error": "未登入或此帳號未獲授權"}), 401
        request.gm_email = email
        return view_func(*args, **kwargs)

    return wrapper


@app.route("/auth/status", methods=["GET"])
def auth_status():
    """
    給前端在登入後(或每次重新整理頁面、靜默重新取得 token 後)確認用:
    這個 Google 帳號的登入憑證有效嗎?這個 email 在主持人白名單裡嗎?

    刻意獨立於 require_gm_email 之外(不共用那個裝飾器)——這支本身的
    用途就是「檢查授權狀態」,token 無效或未授權不算這支 API 本身失敗,
    是正常會發生的查詢結果,所以用 200 + authorized:false 表示,
    只有真的没帶 token / token 完全解不開,才回 401。

    範例:GET /auth/status(需帶 Authorization: Bearer <ID Token>)
    """
    token = auth.extract_bearer_token(request)

    try:
        email = auth.verify_google_id_token(token)
    except auth.VerificationUnavailable:
        # 跟 401 分開:401 是「你的登入無效」(前端該登出),
        # 503 是「我現在驗不了」(前端該保留登入狀態、稍後重試)。
        return jsonify({"authorized": False, "error": "目前無法驗證登入狀態,請稍後再試"}), 503

    if email is None:
        return jsonify({"authorized": False, "error": "登入憑證無效或已過期"}), 401

    return jsonify({"authorized": gm.is_valid_gm_email(email), "email": email}), 200


@app.route("/record", methods=["GET"])
@require_gm_email
def get_record():
    """
    依日期時間查詢場次檔案是否存在,純查詢,不會建立任何東西。
    範例:GET /record?datetime=2026_07_01_18_30(需帶 Authorization: Bearer <ID Token>)

    找到的 spreadsheet_id,前端要記住,之後每次呼叫 /round 都要附帶這個參數
    (後端是無狀態設計,不會自己記住「目前是哪一場」)。

    200 = 找到既有檔案
    404 = 查無此檔案(前端可據此詢問使用者是否要建立新場次,再打 POST /record)
    400 = datetime 格式不合法
    401 = 未登入或此帳號未獲授權
    """
    datetime_str = request.args.get("datetime")

    if not datetime_str:
        return jsonify({"error": "缺少必要參數 datetime"}), 400

    try:
        spreadsheet_id = record_data.find_record(datetime_str)
    except ValueError as e:
        # datetime 格式不合法
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        # 其他非預期錯誤(例如 Drive API 連線失敗、OAuth 憑證過期)
        return jsonify({"error": f"查詢場次檔案時發生錯誤:{str(e)}"}), 500

    if spreadsheet_id is None:
        return jsonify({"error": "查無此場次檔案"}), 404

    return jsonify({"spreadsheet_id": spreadsheet_id}), 200


@app.route("/record", methods=["POST"])
@require_gm_email
def create_record():
    """
    複製 Template 建立新的場次檔案,並把這位主持人的 email 加為編輯者。
    範例:POST /record?datetime=2026_07_01_18_30(需帶 Authorization: Bearer <ID Token>)

    只負責建立,不會先檢查是否已存在(是否該建立由前端決定,通常是在
    GET /record 回傳 404 之後,使用者確認要建立才會打這支)。

    Apps Script 是同步操作,回應時新檔案已確定複製完成,
    回傳的 spreadsheet_id 可以直接拿去用,不需要事後再打 GET 確認。

    201 = 建立成功
    500 = 建立失敗(例如 Apps Script 連不上、密語不對、Drive 發生問題)
    400 = datetime 格式不合法
    401 = 未登入或此帳號未獲授權
    """
    datetime_str = request.args.get("datetime")
    email = request.gm_email  # 已經過 @require_gm_email 驗證過的真實 email,不是使用者自己填的

    if not datetime_str:
        return jsonify({"error": "缺少必要參數 datetime"}), 400

    try:
        spreadsheet_id, warning = record_data.create_record(datetime_str, email)
    except ValueError as e:
        # datetime 格式不合法
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        # 其他非預期錯誤(例如 Apps Script 連線失敗、密語不對、Drive 發生問題)
        return jsonify({"error": f"建立場次檔案時發生錯誤:{str(e)}"}), 500

    result = {"spreadsheet_id": spreadsheet_id}
    if warning:
        # 檔案本身建立成功,但加編輯者這個附加動作失敗(例如 email 格式有誤),
        # 不影響主流程判定為成功(201),只是額外提醒一下
        result["warning"] = warning

    return jsonify(result), 201


@app.route("/round", methods=["GET"])
@limiter.limit(
    "30 per minute",
    # 只有「真的通過驗證」的請求才扣額度。
    #
    # Flask-Limiter 的檢查是在 before_request 做的,一定early於路由裡的
    # 身分驗證,所以預設情況下連 401 都會照扣——實測:連續送 35 個完全
    # 沒帶 token 的請求,前 30 個扣光額度、後 5 個回 429。等於任何人不用
    # 登入就能把所有主持人鎖在門外一整分鐘,而且這些請求根本碰不到
    # Google Sheets,扣它們的額度也保護不到任何東西。
    #
    # deduct_when 讓「檢查」照舊、但「扣款」延到回應產生後再依狀態碼決定:
    # 401(未授權)/503(暫時驗不了)都不扣,額度只反映真正會去讀 Sheet 的流量。
    deduct_when=lambda response: response.status_code not in (401, 503),
)
@require_gm_email
def round_status():
    """
    讀取指定回合的角色狀態表,包含五位角色的事業等級/金錢/積分、
    合法/非法事業總和、三個全域轉換開關(oniwara_out/mike_out/kouno_single)。
    範例:GET /round?day=1st&type=Morning&spreadsheet_id=abc123...(需帶 Authorization: Bearer <ID Token>)

    spreadsheet_id 通常來自 GET /record 回傳的值;不帶這個參數時,
    會 fallback 用 config.SPREADSHEET_ID(本機測試用的預設檔案)。

    完整回應格式範例見 parse_data.build_round_response 的實作。
    """
    day = request.args.get("day")
    type_ = request.args.get("type")
    spreadsheet_id = request.args.get("spreadsheet_id")

    if not day or not type_:
        return jsonify({"error": "缺少必要參數 day 或 type"}), 400

    try:
        result = parse_data.build_round_response(day, type_, spreadsheet_id)
    except ValueError as e:
        # 參數不合法(例如 day 打錯字、type 拼錯),回傳 400 讓呼叫端知道是自己傳錯
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        # 其他非預期錯誤(例如 Sheet 連線失敗、頁籤不存在),回傳 500
        return jsonify({"error": f"讀取資料時發生錯誤:{str(e)}"}), 500

    return jsonify(result), 200


@app.route("/status", methods=["GET"])
def status():
    """
    健康檢查 API。
    用途1:確認伺服器有正常啟動、能回應。
    用途2(未來):給外部排程器(GitHub Actions / UptimeRobot)定期呼叫,
                防止 Render 免費方案因閒置而休眠。
    """
    return jsonify({
        "status": "ok",
        "message": "Fireless War backend is running"
    }), 200


@app.errorhandler(429)
def handle_rate_limit(e):
    return jsonify({"error": "請求太頻繁,請稍後再試"}), 429


if __name__ == "__main__":
    # 本地開發用,Render 部署時不會走到這一段(改用 gunicorn 啟動)
    app.run(host="0.0.0.0", port=5001, debug=True)
