"""キャプチャした映像パケットを H.265（Annex B）へ変換する（開発用ツール）。

入力は次のどちらか:
  - --format lenprefixed: [4 バイト長][RTP パケット] の繰り返し（live_capture.py の保存形式）
  - --format raw:         1 個のファイルに RTP パケットを連結（vf_9061.bin 形式。90 61/90 e1 で区切る）

I スライス（IDR）は E2E 暗号化されているため、--key/--iv（または環境変数
`EUFY_MEDIA_KEY`/`EUFY_MEDIA_IV` = セッションの crypto_key/crypto_iv）を渡すと復号する。

使い方:
  EUFY_MEDIA_KEY=<crypto_key> EUFY_MEDIA_IV=<crypto_iv> \
    python3 tools/packets_to_annexb.py appstream.bin -o out.h265
  ffmpeg -i out.h265 -fps_mode passthrough out_%04d.png
"""

from __future__ import annotations

import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from leo_rtc.video import (Depacketizer, HEVC_PARAMETER_SETS, decrypt_idr,
                            decrypt_parameter_nal, to_annexb)


def iter_lenprefixed(path: str):
    with open(path, 'rb') as fh:
        while True:
            head = fh.read(4)
            if len(head) < 4:
                return
            (ln,) = struct.unpack('<I', head)
            pkt = fh.read(ln)
            if len(pkt) < ln:
                return
            yield pkt


def iter_raw(path: str):
    """RTP パケット連結（vf_9061.bin 形式）を 1 パケットずつ返す。

    パケット境界は「`90 61`/`90 e1` + SSRC `0dc1a815`」の候補位置で判定する
    （ペイロード中の偶然一致は SSRC 4 バイトでほぼ排除できる）。
    """
    data = open(path, 'rb').read()
    offs = []
    i = 0
    while True:
        cands = [x for x in (data.find(b'\x90\x61', i), data.find(b'\x90\xe1', i)) if x >= 0]
        if not cands:
            break
        i = min(cands)
        if i + 24 <= len(data) and data[i + 8:i + 12] == b'\x0d\xc1\xa8\x15':
            offs.append(i)
        i += 1
    for a, b in zip(offs, offs[1:] + [len(data)]):
        yield data[a:b]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description='映像パケットを Annex B H.265 へ変換する')
    ap.add_argument('input', nargs='+', help='入力ファイル（raw 形式では vf_9061.bin と vf_90e1.bin を両方渡す）')
    ap.add_argument('-o', '--output', required=True, help='出力 .h265')
    ap.add_argument('--format', choices=('lenprefixed', 'raw'), default='lenprefixed')
    ap.add_argument('--key', default=os.environ.get('EUFY_MEDIA_KEY'), help='crypto_key（16 文字）')
    ap.add_argument('--iv', default=os.environ.get('EUFY_MEDIA_IV'), help='crypto_iv（12 文字）')
    args = ap.parse_args(argv)

    key = args.key.encode() if args.key else None
    iv = args.iv.encode() if args.iv else None
    if args.format == 'lenprefixed':
        packets = []
        for path in args.input:
            packets.extend(iter_lenprefixed(path))
    else:
        packets = []
        for path in args.input:
            packets.extend(iter_raw(path))
        packets.sort(key=lambda p: p[4:8])
    dep = Depacketizer()
    nals = []
    packets_seen = 0
    for pkt in packets:
        packets_seen += 1
        try:
            nals.extend(dep.feed(pkt))
        except ValueError:
            continue
    nals.extend(dep.flush())
    idr_ok = idr_fail = 0
    first_params: dict[int, bytes] = {}
    if key and iv:
        out_nals = []
        for n in nals:
            t = (n[0] >> 1) & 0x3F
            if t in (32, 33, 34):
                try:
                    n = decrypt_parameter_nal(n, key, iv)
                except ValueError:
                    continue
                first_params.setdefault(t, n)
                out_nals.append(n)  # 解像度切替があるため元の位置に挿入する
                continue
            if t in (19, 20):
                try:
                    n = decrypt_idr(n, key, iv)
                    idr_ok += 1
                except ValueError:
                    idr_fail += 1
            out_nals.append(n)
        nals = out_nals
    parameters = b''.join(b'\x00\x00\x00\x01' + first_params[t] for t in (32, 33, 34) if t in first_params)
    with open(args.output, 'wb') as fh:
        fh.write(to_annexb(nals, parameters=parameters or HEVC_PARAMETER_SETS))
    print(f'packets={packets_seen} nals={len(nals)} incomplete={dep.incomplete} '
          f'idr_ok={idr_ok} idr_fail={idr_fail} params={"wire" if parameters else "default"} -> {args.output}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
