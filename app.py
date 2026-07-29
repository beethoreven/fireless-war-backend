"""
願浮沉2:無火戰爭 —— 後端 API
Stage 1 最小可行版本:先確保伺服器活著、能回應 200
"""

from flask import Flask, jsonify, request

import parse_data

app = Flask(__name__)
app.json.ensure_ascii = False


@app.route("/round", methods=["GET"])
def round_status():
    """
    讀取指定回合的角色狀態表。
    範例:GET /round?day=1st&type=Morning
    """
    day = request.args.get("day")
    type_ = request.args.get("type")

    if not day or not type_:
        return jsonify({"error": "缺少必要參數 day 或 type"}), 400

    try:
        data = parse_data.parse_round_status(day, type_)
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
