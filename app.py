"""
願浮沉2:無火戰爭 —— 後端 API
"""

from flask import Flask, jsonify, request

import parse_data
import record_data

app = Flask(__name__)
app.json.ensure_ascii = False


@app.route("/record", methods=["GET"])
def get_record():
    """
    依日期時間查詢場次檔案是否存在,純查詢,不會建立任何東西。
    範例:GET /record?datetime=2026_07_01_18_30

    找到的 spreadsheet_id,前端要記住,之後每次呼叫 /round 都要附帶這個參數
    (後端是無狀態設計,不會自己記住「目前是哪一場」)。

    200 = 找到既有檔案
    404 = 查無此檔案(前端可據此詢問使用者是否要建立新場次,再打 POST /record)
    400 = datetime 格式不合法
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
def create_record():
    """
    複製 Template 建立新的場次檔案。
    範例:POST /record?datetime=2026_07_01_18_30

    只負責建立,不會先檢查是否已存在(是否該建立由前端決定,通常是在
    GET /record 回傳 404 之後,使用者確認要建立才會打這支)。

    Drive 的 files.copy 是同步 API,回應時新檔案已確定複製完成,
    回傳的 spreadsheet_id 可以直接拿去用,不需要事後再打 GET 確認。

    201 = 建立成功
    500 = 建立失敗(例如 Drive API 連線失敗、OAuth 憑證過期、額度問題)
    400 = datetime 格式不合法
    """
    datetime_str = request.args.get("datetime")

    if not datetime_str:
        return jsonify({"error": "缺少必要參數 datetime"}), 400

    try:
        spreadsheet_id = record_data.create_record(datetime_str)
    except ValueError as e:
        # datetime 格式不合法
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        # 其他非預期錯誤(例如 Drive API 連線失敗、OAuth 憑證過期、額度問題)
        return jsonify({"error": f"建立場次檔案時發生錯誤:{str(e)}"}), 500

    return jsonify({"spreadsheet_id": spreadsheet_id}), 201


@app.route("/round", methods=["GET"])
def round_status():
    """
    讀取指定回合的角色狀態表。
    範例:GET /round?day=1st&type=Morning&spreadsheet_id=abc123...

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
