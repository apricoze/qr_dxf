from __future__ import annotations

import io
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Tuple

import ezdxf
from flask import Flask, jsonify, render_template, request, send_file
import qrcode
from qrcode.constants import ERROR_CORRECT_H, ERROR_CORRECT_L, ERROR_CORRECT_M, ERROR_CORRECT_Q


class ErrorCorrection(str, Enum):
    L = "L"
    M = "M"
    Q = "Q"
    H = "H"

    @property
    def qr_constant(self) -> int:
        return {
            ErrorCorrection.L: ERROR_CORRECT_L,
            ErrorCorrection.M: ERROR_CORRECT_M,
            ErrorCorrection.Q: ERROR_CORRECT_Q,
            ErrorCorrection.H: ERROR_CORRECT_H,
        }[self]


@dataclass
class QRRequest:
    data: str
    error_correction: ErrorCorrection
    border: int
    module_size: float

    @classmethod
    def from_request(cls, req: request) -> "QRRequest":
        payload: Dict[str, str] = req.get_json(force=True, silent=True) or {}
        data = (payload.get("data") or "").strip()
        if not data:
            raise ValueError("入力テキストを指定してください。")

        try:
            error_correction = ErrorCorrection(payload.get("errorCorrection", "M"))
        except ValueError as exc:  # pragma: no cover - defensive programming
            raise ValueError("不明な誤り訂正レベルが指定されました。") from exc

        try:
            border = int(payload.get("border", 4))
        except (TypeError, ValueError) as exc:
            raise ValueError("余白の値は整数で指定してください。") from exc
        if border < 0:
            raise ValueError("余白の値は0以上である必要があります。")

        try:
            module_size = float(payload.get("moduleSize", 1.0))
        except (TypeError, ValueError) as exc:
            raise ValueError("モジュールサイズは数値で指定してください。") from exc
        if module_size <= 0:
            raise ValueError("モジュールサイズは正の数である必要があります。")

        return cls(
            data=data,
            error_correction=error_correction,
            border=border,
            module_size=module_size,
        )


def create_qr_code(data: str, error_correction: ErrorCorrection, border: int) -> qrcode.QRCode:
    qr = qrcode.QRCode(
        version=None,
        error_correction=error_correction.qr_constant,
        box_size=10,
        border=border,
    )
    qr.add_data(data)
    qr.make(fit=True)
    return qr


def matrix_to_dxf(matrix: Tuple[Tuple[bool, ...], ...], module_size: float) -> io.BytesIO:
    doc = ezdxf.new(setup=True)
    msp = doc.modelspace()

    size = len(matrix)
    for y, row in enumerate(matrix):
        for x, cell in enumerate(row):
            if not cell:
                continue
            # 原点を左下に揃えるためにY座標を反転させる
            x0 = x * module_size
            y0 = (size - y - 1) * module_size
            x1 = x0 + module_size
            y1 = y0 + module_size
            msp.add_lwpolyline(
                [(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
                format="xy",
                close=True,
            )

    buffer = io.BytesIO()
    doc.write(stream=buffer)
    buffer.seek(0)
    return buffer


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index() -> str:
        return render_template("index.html")

    @app.post("/api/qr-dxf")
    def qr_dxf():
        try:
            qr_request = QRRequest.from_request(request)
        except ValueError as exc:
            return jsonify({"message": str(exc)}), 400

        qr_code = create_qr_code(
            qr_request.data,
            qr_request.error_correction,
            qr_request.border,
        )
        matrix = tuple(tuple(row) for row in qr_code.get_matrix())
        buffer = matrix_to_dxf(matrix, qr_request.module_size)
        filename = "qr_code.dxf"
        if qr_request.data:
            filename = f"qr_{qr_request.data[:20].replace(' ', '_')}.dxf"
        return send_file(
            buffer,
            as_attachment=True,
            download_name=filename,
            mimetype="image/vnd.dxf",
        )

    @app.get("/api/qr-preview")
    def qr_preview():
        data = (request.args.get("data") or "").strip()
        if not data:
            return jsonify({"message": "入力テキストを指定してください。"}), 400

        try:
            error_correction = ErrorCorrection(request.args.get("errorCorrection", "M"))
        except ValueError:
            return jsonify({"message": "不明な誤り訂正レベルが指定されました。"}), 400

        try:
            border = int(request.args.get("border", 4))
        except (TypeError, ValueError):
            return jsonify({"message": "余白の値は整数で指定してください。"}), 400
        if border < 0:
            return jsonify({"message": "余白の値は0以上である必要があります。"}), 400

        qr_code = create_qr_code(data, error_correction, border)
        image = qr_code.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        return send_file(buffer, mimetype="image/png")

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
