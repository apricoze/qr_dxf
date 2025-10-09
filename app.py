from __future__ import annotations

import base64
import binascii
import io
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, Mapping, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from flask import Flask, jsonify, render_template, request, send_file
from PIL import Image, ImageDraw
import qrcode
from qrcode.constants import ERROR_CORRECT_H, ERROR_CORRECT_L, ERROR_CORRECT_M, ERROR_CORRECT_Q

from qr_dxf.dxf import qr_matrix_to_dxf
from qr_dxf.matrix_utils import finder_pattern_modules


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
    body_corner_radius: float
    eye_frame_corner_radius: float
    eye_ball_corner_radius: float

    @staticmethod
    def _parse_corner_radius(payload: Mapping[str, object], key: str, label: str) -> float:
        raw_value = payload.get(key, 0)
        if raw_value in (None, ""):
            return 0.0
        try:
            value = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label}の角丸率は数値で指定してください。") from exc
        if not 0.0 <= value <= 50.0:
            raise ValueError(f"{label}の角丸率は0から50の間で指定してください。")
        return value / 100.0

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "QRRequest":
        data = str(payload.get("data") or "").strip()
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

        body_corner_radius = cls._parse_corner_radius(payload, "bodyCornerRadius", "Body")
        eye_frame_corner_radius = cls._parse_corner_radius(payload, "eyeFrameCornerRadius", "Eye Frame")
        eye_ball_corner_radius = cls._parse_corner_radius(payload, "eyeBallCornerRadius", "Eye Ball")

        return cls(
            data=data,
            error_correction=error_correction,
            border=border,
            module_size=module_size,
            body_corner_radius=body_corner_radius,
            eye_frame_corner_radius=eye_frame_corner_radius,
            eye_ball_corner_radius=eye_ball_corner_radius,
        )

    @classmethod
    def from_request(cls, req: request) -> "QRRequest":
        payload: Dict[str, object] = req.get_json(force=True, silent=True) or {}
        return cls.from_payload(payload)


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


def matrix_to_dxf(
    matrix: Tuple[Tuple[bool, ...], ...],
    module_size: float,
    body_corner_radius: float,
    eye_frame_corner_radius: float,
    eye_ball_corner_radius: float,
) -> io.BytesIO:
    dxf_text = qr_matrix_to_dxf(
        matrix,
        module_size=module_size,
        body_corner_radius=module_size * body_corner_radius,
        eye_frame_corner_radius=module_size * eye_frame_corner_radius,
        eye_ball_corner_radius=module_size * eye_ball_corner_radius,
    )
    buffer = io.BytesIO(dxf_text.encode("utf-8"))
    buffer.seek(0)
    return buffer


def render_qr_image(
    matrix: Tuple[Tuple[bool, ...], ...],
    body_corner_radius: float,
    eye_frame_corner_radius: float,
    eye_ball_corner_radius: float,
    box_size: int = 10,
) -> Image.Image:
    size = len(matrix)
    image = Image.new("RGBA", (size * box_size, size * box_size), (255, 255, 255, 255))
    draw = ImageDraw.Draw(image)
    eye_frame_modules, eye_ball_modules = finder_pattern_modules(matrix)

    def _radius_for(x: int, y: int) -> float:
        if (x, y) in eye_ball_modules:
            ratio = eye_ball_corner_radius
        elif (x, y) in eye_frame_modules:
            ratio = eye_frame_corner_radius
        else:
            ratio = body_corner_radius
        return max(0.0, min(ratio * box_size, box_size / 2.0))

    for y, row in enumerate(matrix):
        for x, cell in enumerate(row):
            if not cell:
                continue
            left = x * box_size
            top = y * box_size
            right = left + box_size
            bottom = top + box_size
            radius = _radius_for(x, y)
            if radius <= 0:
                draw.rectangle((left, top, right, bottom), fill=(0, 0, 0, 255))
            else:
                draw.rounded_rectangle(
                    (left, top, right, bottom), radius=radius, fill=(0, 0, 0, 255)
                )

    return image


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


def add_icon_to_image(image: Image.Image, icon_bytes: bytes, icon_scale: float) -> Image.Image:
    try:
        icon = Image.open(io.BytesIO(icon_bytes))
    except (OSError, ValueError):
        return image

    image = image.convert("RGBA")
    icon = icon.convert("RGBA")

    width, height = image.size
    clamped_scale = max(0.01, min(icon_scale, 0.8))
    target_size = max(1, int(min(width, height) * clamped_scale))
    icon.thumbnail((target_size, target_size), Image.LANCZOS)

    icon_w, icon_h = icon.size
    position = ((width - icon_w) // 2, (height - icon_h) // 2)

    padding = max(1, int(min(icon_w, icon_h) * 0.1))
    left = max(0, position[0] - padding)
    top = max(0, position[1] - padding)
    right = min(width, position[0] + icon_w + padding)
    bottom = min(height, position[1] + icon_h + padding)

    ImageDraw.Draw(image).rectangle([(left, top), (right, bottom)], fill=(255, 255, 255, 255))

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
        buffer = matrix_to_dxf(
            matrix,
            qr_request.module_size,
            qr_request.body_corner_radius,
            qr_request.eye_frame_corner_radius,
            qr_request.eye_ball_corner_radius,
        )
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

        try:
            qr_request = QRRequest.from_payload(payload)
        except ValueError as exc:
            return jsonify({"message": str(exc)}), 400

        data = qr_request.data

        icon_bytes = None
        icon_data_url = payload.get("iconData")
        if isinstance(icon_data_url, str):
            icon_bytes = decode_data_url(icon_data_url)

        if icon_bytes is None:
            icon_bytes = fetch_favicon(data)

        try:
            icon_size_percent = float(payload.get("iconSize", 22.0))
        except (TypeError, ValueError):
            return jsonify({"message": "アイコンサイズは数値で指定してください。"}), 400

        if not 5.0 <= icon_size_percent <= 40.0:
            return jsonify({"message": "アイコンサイズは5から40の間で指定してください。"}), 400

        qr_code = create_qr_code(data, qr_request.error_correction, qr_request.border)
        matrix = tuple(tuple(row) for row in qr_code.get_matrix())
        image = render_qr_image(
            matrix,
            qr_request.body_corner_radius,
            qr_request.eye_frame_corner_radius,
            qr_request.eye_ball_corner_radius,
        )

        if icon_bytes:
            image = add_icon_to_image(image, icon_bytes, icon_size_percent / 100)

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        return send_file(buffer, mimetype="image/png")

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
