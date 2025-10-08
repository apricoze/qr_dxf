# QR DXF ツール

ブラウザからテキストを入力し、QRコードのプレビューを確認しながらDXFファイルをダウンロードできるシンプルなツールです。Flask ベースのAPIとシングルページUIで構成されています。

## セットアップ

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 開発サーバーの起動

```bash
flask --app app run --host 0.0.0.0 --port 5000 --debug
```

`http://localhost:5000` をブラウザで開いてGUIを操作します。

## 主な機能

- テキスト入力に応じてリアルタイムにQRコードプレビューを更新
- 誤り訂正レベル・余白・DXFモジュールサイズの調整
- 生成したDXFファイルのダウンロード

## ライセンス

このリポジトリはMITライセンスで公開されています。
