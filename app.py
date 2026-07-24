"""
願浮沉2:無火戰爭 —— 後端 API
Stage 1 最小可行版本:先確保伺服器活著、能回應 200
"""

from flask import Flask, jsonify

app = Flask(__name__)


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
