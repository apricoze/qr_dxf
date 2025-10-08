"""Command line interface for generating DXF QR codes."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

from . import dxf as dxf_export
from . import generator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate QR codes as DXF geometry")
    data_group = parser.add_mutually_exclusive_group(required=True)
    data_group.add_argument("--text", help="Literal text/URL to encode")
    data_group.add_argument("--wifi", action="store_true", help="Encode Wi-Fi credentials")
    data_group.add_argument("--file", type=Path, help="Read the payload from a file")

    parser.add_argument("--ssid", help="Wi-Fi SSID", default="")
    parser.add_argument("--password", help="Wi-Fi password", default="")
    parser.add_argument("--auth", help="Wi-Fi authentication (WEP/WPA/WPA2/nopass)", default="WPA")
    parser.add_argument("--hidden", action="store_true", help="Mark Wi-Fi network as hidden")

    parser.add_argument("-o", "--output", type=Path, default=Path("qr_code.dxf"), help="Output DXF file path")
    parser.add_argument("--module-size", type=float, default=1.0, help="Size of a single module")
    parser.add_argument("--corner-radius", type=float, default=0.0, help="Rounded corner radius")
    parser.add_argument("--rounded", action="store_true", help="Use a default rounded style (25%% of module size)")
    parser.add_argument("--layer", default="QR", help="DXF layer name")
    parser.add_argument("--ecc", choices=["low", "medium", "quartile", "high"], default="medium", help="Error correction level")
    parser.add_argument("--border", type=int, default=4, help="Quiet-zone width in modules")
    return parser


def resolve_payload(args: argparse.Namespace) -> str:
    if args.wifi:
        if not args.ssid:
            raise SystemExit("--ssid is required when using --wifi")
        return generator.build_wifi_payload(args.ssid, password=args.password, auth=args.auth, hidden=args.hidden)
    if args.text is not None:
        return args.text
    if args.file is not None:
        return args.file.read_text(encoding="utf-8")
    raise SystemExit("No payload provided")


def main(argv: Optional[list[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    payload = resolve_payload(args)
    matrix = generator.matrix_from_text(payload, ecc=args.ecc, border=args.border)
    radius = args.corner_radius
    if args.rounded and radius <= 0:
        radius = args.module_size * 0.25
    dxf_text = dxf_export.qr_matrix_to_dxf(matrix, module_size=args.module_size, corner_radius=radius, layer=args.layer)
    args.output.write_text(dxf_text, encoding="utf-8")
    parser.exit(0, f"Saved DXF to {args.output}\n")


if __name__ == "__main__":
    main()
