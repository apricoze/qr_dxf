"""QR data helpers."""

from __future__ import annotations

from typing import List

from . import qrcodegen

_ECC_LEVELS = {
    "low": qrcodegen.QrCode.LOW,
    "medium": qrcodegen.QrCode.MEDIUM,
    "quartile": qrcodegen.QrCode.QUARTILE,
    "high": qrcodegen.QrCode.HIGH,
}


def build_wifi_payload(ssid: str, password: str = "", auth: str = "WPA", hidden: bool = False) -> str:
    """Return the Wi-Fi QR payload string."""
    auth_normalized = auth.upper()
    valid_auth = {"WEP", "WPA", "WPA2", "WPA/WPA2", "NOPASS"}
    if auth_normalized not in valid_auth:
        raise ValueError("auth must be WEP, WPA, WPA2, WPA/WPA2, or nopass")
    def _escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace(";", r"\;").replace(",", r"\,").replace(":", r"\:")

    escaped_ssid = _escape(ssid)
    escaped_pwd = _escape(password) if auth_normalized != "NOPASS" else ""
    hidden_flag = "true" if hidden else "false"
    return f"WIFI:T:{auth_normalized};S:{escaped_ssid};P:{escaped_pwd};H:{hidden_flag};;"


def matrix_from_text(text: str, ecc: str = "medium", border: int = 4) -> List[List[bool]]:
    """Encode ``text`` into a matrix of booleans representing the QR code."""
    try:
        ecl = _ECC_LEVELS[ecc.lower()]
    except KeyError as exc:
        raise ValueError(f"unknown ECC level: {ecc}") from exc
    qr = qrcodegen.QrCode.encode_text(text, ecl)
    return _add_border(qr.get_matrix(), border)


def matrix_from_bytes(data: bytes, ecc: str = "medium", border: int = 4) -> List[List[bool]]:
    try:
        ecl = _ECC_LEVELS[ecc.lower()]
    except KeyError as exc:
        raise ValueError(f"unknown ECC level: {ecc}") from exc
    qr = qrcodegen.QrCode.encode_binary(data, ecl)
    return _add_border(qr.get_matrix(), border)


def _add_border(matrix: List[List[bool]], border: int) -> List[List[bool]]:
    if border <= 0:
        return [row[:] for row in matrix]
    size = len(matrix)
    new_size = size + border * 2
    result = [[False] * new_size for _ in range(new_size)]
    for y, row in enumerate(matrix):
        for x, value in enumerate(row):
            result[y + border][x + border] = value
    return result
