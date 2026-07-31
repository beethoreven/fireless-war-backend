"""
願浮沉2:無火戰爭 —— 後端 API
"""

from functools import wraps

from flask import Flask, jsonify, request
from flask_cors import CORS

import gm
import parse_data
import record_data

app = Flask(__name__)
app.json.ensure_ascii = False

# 前端(GitHub Pages)透過瀏覽器 fetch 呼叫這裡,需要 CORS 允許來源網域。
# 本機開發(任意 port 的 localhost/127.0.0.1)也一併放行方便測試。
CORS(
    app,
    origins=[
        "https://beethoreven.github.io",
        r"http://localhost:\d+",
        r"http://127\.0\.0\.1:\d+",
    ],
)


def require_gm_email(view_func):
    """
    裝飾器:檢查請求有沒有帶合法的 email 參數(白名單裡的主持人)。
    不合法或沒帶,直接擋下回 401,不會進到實際的路由邏輯。

    注意這不是真正的身分驗證,詳見 gm.py 開頭的說明。
    """

    @wraps(view_func)
    def wrapper(*args, **kwargs):
        email = request.args.get("email")
        if not gm.is_valid_gm_email(email):
            return jsonify({"error": "email 未提供或未授權"}), 401
        return view_func(*args, **kwargs)

    return wrapper


@app.route("/record", methods=["GET"])
@require_gm_email
def get_record():
    """
    依日期時間查詢場次檔案是否存在,純查詢,不會建立任何東西。
    範例:GET /record?datetime=2026_07_01_18_30&email=beethoreven@gmail.com

    找到的 spreadsheet_id,前端要記住,之後每次呼叫 /round 都要附帶這個參數
    (後端是無狀態設計,不會自己記住「目前是哪一場」)。

    200 = 找到既有檔案
    404 = 查無此檔案(前端可據此詢問使用者是否要建立新場次,再打 POST /record)
    400 = datetime 格式不合法
    401 = email 未提供或未授權
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
    範例:POST /record?datetime=2026_07_01_18_30&email=beethoreven@gmail.com

    只負責建立,不會先檢查是否已存在(是否該建立由前端決定,通常是在
    GET /record 回傳 404 之後,使用者確認要建立才會打這支)。

    Apps Script 是同步操作,回應時新檔案已確定複製完成,
    回傳的 spreadsheet_id 可以直接拿去用,不需要事後再打 GET 確認。

    201 = 建立成功
    500 = 建立失敗(例如 Apps Script 連不上、密語不對、Drive 發生問題)
    400 = datetime 格式不合法
    401 = email 未提供或未授權
    """
    datetime_str = request.args.get("datetime")
    email = request.args.get("email")  # 已經過 @require_gm_email 驗證,這裡一定是合法值

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
@require_gm_email
def round_status():
    """
    讀取指定回合的角色狀態表。
    範例:GET /round?day=1st&type=Morning&spreadsheet_id=abc123...&email=beethoreven@gmail.com

    spreadsheet_id 通常來自 GET /record 回傳的值;不帶這個參數時,
    會 fallback 用 config.SPREADSHEET_ID(本機測試用的預設檔案)。
    """
    day = request.args.get("day")
    type_ = request.args.get("type")
    spreadsheet_id = request.args.get("spreadsheet_id")

    if not day or not type_:
        return jsonify({"error": "缺少必要參數 day 或 type"}), 400

    try:
        data = parse_data.parse_round_status(day, type_, spreadsheet_id)
    except ValueError as e:
        # 參數不合法(例如 day 打錯字、type 拼錯),回傳 400 讓呼叫端知道是自己傳錯
        return jsonify({"error": str(e)}), 400
    except NotImplementedError as e:
        # 這個回合類型的解析邏輯還沒做完(目前是一般 Report 頁籤),明確回 501
        return jsonify({"error": str(e)}), 501
    except Exception as e:
        # 其他非預期錯誤(例如 Sheet 連線失敗、頁籤不存在),回傳 500
        return jsonify({"error": f"讀取資料時發生錯誤:{str(e)}"}), 500

    return jsonify({"day": day, "type": type_, "data": data}), 200


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


if __name__ == "__main__":
    # 本地開發用,Render 部署時不會走到這一段(改用 gunicorn 啟動)
    app.run(host="0.0.0.0", port=5001, debug=True)
