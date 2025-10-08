# QR DXF Generator

コマンドラインでURLやWi-Fi接続情報などをQRコード化し、CADや3Dモデリングで扱いやすいDXFファイルとして出力するツールです。セル(モジュール)サイズや角の丸みを調整して、モデリングデータとして使いやすい形状を生成できます。

## インストール

Python 3.10 以上が必要です。ソースツリー直下で `src` ディレクトリを `PYTHONPATH` に追加するか、`pip install -e .` でインストールしてください。

## 使い方

### URLなど任意のテキストをDXF化

```bash
PYTHONPATH=src python -m qr_dxf --text "https://example.com" --output example.dxf --module-size 1.0 --rounded
```

### Wi-Fi 接続情報をQRコード化

```bash
PYTHONPATH=src python -m qr_dxf --wifi --ssid MyNetwork --password secretpass \
  --auth WPA2 --rounded --module-size 1.5 --corner-radius 0.4 --output wifi_qr.dxf
```

主なオプション:

- `--module-size`: 1セルのサイズ(既定値: 1.0)
- `--corner-radius`: 角丸半径。`--rounded` を指定するとモジュールサイズの25%が自動で設定されます。
- `--ecc`: 誤り訂正レベル(`low`/`medium`/`quartile`/`high`)
- `--border`: クワイエットゾーン(余白)のセル数
- `--layer`: DXFレイヤー名

出力されるDXFは各セルを `LWPOLYLINE` で表現しており、角丸の場合はDXFの bulge 値を使用した円弧で構成されます。CAD上で押し出し等の3D加工を行う際もスムーズに扱えます。

## モジュールとしての利用

```python
from qr_dxf import matrix_from_text, qr_matrix_to_dxf

matrix = matrix_from_text("Hello QR", ecc="high")
dxf = qr_matrix_to_dxf(matrix, module_size=2.0, corner_radius=0.5)
with open("hello.dxf", "w", encoding="utf-8") as fh:
    fh.write(dxf)
```

## ライセンス

ソースコードはすべて MIT ライセンスで提供しています。
