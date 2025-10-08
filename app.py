from __future__ import annotations

import base64
import binascii
import io
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import ezdxf
from flask import Flask, jsonify, render_template, request, send_file
from PIL import Image
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


def decode_data_url(data_url: str) -> Optional[bytes]:
    if not data_url:
        return None

    if not data_url.startswith("data:"):
        return None

    try:
        header, encoded = data_url.split(",", 1)
    except ValueError:
        return None

    if "base64" not in header:
        return None

    try:
        return base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        return None


def fetch_favicon(url: str) -> Optional[bytes]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None

    favicon_url = f"{parsed.scheme}://{parsed.netloc}/favicon.ico"
    request = Request(favicon_url, headers={"User-Agent": "Mozilla/5.0"})

    try:
        with urlopen(request, timeout=5) as response:
            content = response.read()
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        return None

    if not content or len(content) > 1_000_000:
        return None

    return content


def add_icon_to_image(image: Image.Image, icon_bytes: bytes) -> Image.Image:
    try:
        icon = Image.open(io.BytesIO(icon_bytes))
    except (OSError, ValueError):
        return image

    image = image.convert("RGBA")
    icon = icon.convert("RGBA")

    width, height = image.size
    target_size = max(1, int(min(width, height) * 0.22))
    icon.thumbnail((target_size, target_size), Image.LANCZOS)

    icon_w, icon_h = icon.size
    position = ((width - icon_w) // 2, (height - icon_h) // 2)

    image.paste(icon, position, mask=icon)
    return image


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

    @app.route("/api/qr-preview", methods=["GET", "POST"])
    def qr_preview():
        if request.method == "GET":
            payload = {key: value for key, value in request.args.items()}
        else:
            payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            payload = {}
        data = (payload.get("data") or "").strip()
        if not data:
            return jsonify({"message": "入力テキストを指定してください。"}), 400

        try:
            error_correction = ErrorCorrection(payload.get("errorCorrection", "M"))
        except ValueError:
            return jsonify({"message": "不明な誤り訂正レベルが指定されました。"}), 400

        try:
            border = int(payload.get("border", 4))
        except (TypeError, ValueError):
            return jsonify({"message": "余白の値は整数で指定してください。"}), 400
        if border < 0:
            return jsonify({"message": "余白の値は0以上である必要があります。"}), 400

        icon_bytes = None
        icon_data_url = payload.get("iconData")
        if isinstance(icon_data_url, str):
            icon_bytes = decode_data_url(icon_data_url)

        if icon_bytes is None:
            icon_bytes = fetch_favicon(data)

        qr_code = create_qr_code(data, error_correction, border)
        image = qr_code.make_image(fill_color="black", back_color="white").convert("RGBA")

        if icon_bytes:
            image = add_icon_to_image(image, icon_bytes)

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        return send_file(buffer, mimetype="image/png")

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
