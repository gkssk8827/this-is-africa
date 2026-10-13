"""
extract_screenshot.py
======================
방송 영상(구글 드라이브에서 다운로드한 mp4 등)에서 지정한 타임스탬프의 프레임을
정지 이미지로 뽑아 저장하는 스크립트. `broadcast` 카테고리 글에서 image-maker가
GPT 생성 사진 대신 실제 방송 화면 캡처를 쓰고 싶을 때 사용한다.

⚠️ 저작권 유의: 여기서 추출하는 화면은 TIA가 만든 사진이 아니라 방송사(넷플릭스/KBS 등)가
저작권을 가진 영상의 일부다. 블로그는 TIA 자신의 방송 참여를 소개/리뷰하는 목적이라 해도,
과도한 장면 수를 쓰거나 원본 화질 그대로 크게 게시하는 것은 저작권 리스크를 키운다.
가능하면 글당 1~2장, 설명/비평 목적에 필요한 최소한만 사용하고, 화질을 살짝 낮추는 것을
권장한다(아래 --scale 옵션). 확신이 없으면 발행 전 사용자에게 사용 가능 여부를 확인할 것.

사용 예시
---------
1) 영상 전체 정보 확인 (길이, 해상도 등 — 타임스탬프 잡기 전에 참고용):
   python scripts/extract_screenshot.py info --video output/[주제]/raw/broadcast.mp4

2) 단일 타임스탬프에서 캡처 1장:
   python scripts/extract_screenshot.py capture \
       --video output/[주제]/raw/broadcast.mp4 \
       --timestamp 00:03:45 \
       --out output/[주제]/images/image-01.jpg

3) 여러 타임스탬프를 한 번에 (JSON 목록):
   python scripts/extract_screenshot.py capture-batch \
       --video output/[주제]/raw/broadcast.mp4 \
       --spec '[{"timestamp": "00:03:45", "out": "output/[주제]/images/image-01.jpg"}, {"timestamp": "00:07:12", "out": "output/[주제]/images/image-02.jpg"}]'

타임스탬프 형식: "HH:MM:SS" 또는 "MM:SS" 또는 초 단위 숫자("225") 모두 허용.

⚠️ **속도 최적화(2026-07-16)**: `--out`을 `.png`가 아니라 `.jpg`로 지정할 것을 권장한다.
PNG 대비 파일 용량이 1/5~1/6로 줄어(육안상 화질 차이는 거의 없음), publish.py의
이미지 업로드 단계가 파일 용량에 비례해 오래 걸리는 문제를 크게 줄여준다(실측:
PNG 스크린샷 1장 평균 1.2MB, 업로드에 수십 초 소요). `--jpg-quality`(기본 3, ffmpeg
`-q:v` 기준 2~5 권장)로 화질을 조절할 수 있다. 무손실이 꼭 필요한 경우에만 `.png`를 쓴다.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def log(msg: str):
    print(f"[extract_screenshot] {msg}")


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def check_ffmpeg():
    try:
        r = _run(["ffmpeg", "-version"])
    except FileNotFoundError:
        log("ffmpeg를 찾을 수 없습니다. 이 환경에 ffmpeg가 설치되어 있는지 확인하세요 (macOS: `brew install ffmpeg`).")
        sys.exit(1)
    if r.returncode != 0:
        log("ffmpeg를 찾을 수 없습니다. 이 환경에 ffmpeg가 설치되어 있는지 확인하세요 (macOS: `brew install ffmpeg`).")
        sys.exit(1)


def cmd_info(args):
    check_ffmpeg()
    video = Path(args.video)
    if not video.exists():
        log(f"영상 파일이 없습니다: {video}")
        sys.exit(1)
    r = _run(["ffprobe", "-v", "error", "-show_entries",
              "format=duration:stream=width,height,r_frame_rate",
              "-of", "default=noprint_wrappers=1", str(video)])
    if r.returncode != 0:
        log(f"ffprobe 실패: {r.stderr}")
        sys.exit(1)
    print(r.stdout)


def extract_frame(video: Path, timestamp: str, out: Path, scale_width: int | None, jpg_quality: int = 3):
    """지정 타임스탬프에서 프레임 1장을 추출한다.

    2026-07-16: `.jpg`/`.jpeg` 확장자로 저장하면 ffmpeg가 자동으로 JPEG 인코딩하는데,
    `-q:v 3`(ffmpeg 기준 2~5가 고화질) 수준이면 PNG 대비 파일 용량이 약 1/5~1/6로
    줄어들면서도 블로그 스크린샷 용도로는 육안상 차이가 거의 없다. 발행 스크립트의
    이미지 업로드 시간은 파일 용량에 비례해 오래 걸리므로(실측: PNG 1장당 수십 초),
    `.png` 대신 `.jpg` 출력을 기본으로 권장한다(`.png`로 지정하면 그대로 무손실 PNG로
    저장되니 필요하면 계속 PNG도 쓸 수 있다).
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    # -ss를 -i 앞에 둬서 빠른 seek 사용 (정확도는 약간 떨어질 수 있으나 방송 캡처 용도로는 충분)
    cmd = ["ffmpeg", "-y", "-ss", str(timestamp), "-i", str(video), "-frames:v", "1"]
    if scale_width:
        cmd += ["-vf", f"scale={scale_width}:-1"]
    if out.suffix.lower() in (".jpg", ".jpeg"):
        cmd += ["-q:v", str(jpg_quality)]
    cmd += [str(out)]
    r = _run(cmd)
    if r.returncode != 0 or not out.exists():
        log(f"프레임 추출 실패 (timestamp={timestamp}): {r.stderr[-500:]}")
        return False
    log(f"저장 완료: {out} (timestamp={timestamp})")
    return True


def cmd_capture(args):
    check_ffmpeg()
    video = Path(args.video)
    if not video.exists():
        log(f"영상 파일이 없습니다: {video}")
        sys.exit(1)
    out = Path(args.out)
    ok = extract_frame(video, args.timestamp, out, args.scale, args.jpg_quality)
    sys.exit(0 if ok else 1)


def cmd_capture_batch(args):
    check_ffmpeg()
    video = Path(args.video)
    if not video.exists():
        log(f"영상 파일이 없습니다: {video}")
        sys.exit(1)
    try:
        spec = json.loads(args.spec)
    except json.JSONDecodeError as e:
        log(f"--spec JSON 파싱 실패: {e}")
        sys.exit(1)

    fail_count = 0
    for item in spec:
        ok = extract_frame(video, item["timestamp"], Path(item["out"]), args.scale, args.jpg_quality)
        if not ok:
            fail_count += 1

    if fail_count:
        log(f"{fail_count}건 실패. 실패한 타임스탬프는 재시도하거나 다른 시점으로 다시 요청하세요.")
        sys.exit(1)
    log(f"전체 {len(spec)}건 캡처 완료.")


def main():
    parser = argparse.ArgumentParser(description="방송 영상에서 타임스탬프 기준으로 스크린샷 추출")
    sub = parser.add_subparsers(dest="command", required=True)

    info = sub.add_parser("info", help="영상 길이/해상도 등 메타정보 확인")
    info.add_argument("--video", required=True)
    info.set_defaults(func=cmd_info)

    cap = sub.add_parser("capture", help="타임스탬프 1개에서 프레임 1장 추출")
    cap.add_argument("--video", required=True)
    cap.add_argument("--timestamp", required=True, help='"HH:MM:SS", "MM:SS", 또는 초 단위 숫자')
    cap.add_argument("--out", required=True)
    cap.add_argument("--scale", type=int, default=1280, help="가로 픽셀 기준 리사이즈 (기본 1280, 0이면 원본 유지)")
    cap.add_argument("--jpg-quality", type=int, default=3, dest="jpg_quality",
                      help="--out이 .jpg/.jpeg일 때 ffmpeg -q:v 값(2~5 권장, 낮을수록 고화질/큰 용량, 기본 3)")
    cap.set_defaults(func=cmd_capture)

    batch = sub.add_parser("capture-batch", help="여러 타임스탬프를 JSON 목록으로 한 번에 추출")
    batch.add_argument("--video", required=True)
    batch.add_argument("--spec", required=True, help='[{"timestamp": "...", "out": "..."}, ...] 형식 JSON 문자열')
    batch.add_argument("--scale", type=int, default=1280)
    batch.add_argument("--jpg-quality", type=int, default=3, dest="jpg_quality",
                        help="--out이 .jpg/.jpeg일 때 ffmpeg -q:v 값(2~5 권장, 기본 3)")
    batch.set_defaults(func=cmd_capture_batch)

    args = parser.parse_args()
    if hasattr(args, "scale") and args.scale == 0:
        args.scale = None
    args.func(args)


if __name__ == "__main__":
    main()
