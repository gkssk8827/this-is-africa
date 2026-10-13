"""
실사 사진 생성 스크립트 (GPT Image API 사용)

사용법:
    python scripts/generate_photo.py "프롬프트 내용" output/[주제]/images/photo1.png

환경변수:
    OPENAI_API_KEY - .env 파일 또는 시스템 환경변수에 설정되어 있어야 함
"""

import sys
import os
import base64
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv 미설치 시 시스템 환경변수만 사용

from openai import OpenAI


def generate_photo(
    prompt: str,
    output_path: str,
    size: str = "1536x1024",
    quality: str = "high",
):
    """
    GPT 이미지 API로 실사 사진을 생성해서 파일로 저장한다.

    size 옵션: "1024x1024" (정사각), "1536x1024" (가로), "1024x1536" (세로)
    quality 옵션: "low", "medium", "high"
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY가 설정되어 있지 않습니다. .env 파일을 확인하세요."
        )

    client = OpenAI(api_key=api_key)

    result = client.images.generate(
        model="gpt-image-1",
        prompt=prompt,
        size=size,
        quality=quality,
        n=1,
    )

    image_base64 = result.data[0].b64_json
    image_bytes = base64.b64decode(image_base64)

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_bytes(image_bytes)

    print(f"이미지 생성 완료: {output_file}")
    return str(output_file)


def edit_photo_with_reference(
    prompt: str,
    input_image_paths: list,
    output_path: str,
    size: str = "1024x1024",
    quality: str = "high",
):
    """
    기존 사진(들)을 GPT 이미지 편집 API에 넘겨 텍스트 오버레이 등을 합성한다.
    cover 제작 시 바탕 사진 + 타이포그래피 참고 샘플 이미지를 함께 넘겨서
    "이 폰트 스타일로 이 문구를 넣어줘" 식으로 위임할 때 사용한다.

    input_image_paths: 첫 번째가 바탕 사진(합성 대상), 이후는 참고용 레퍼런스 이미지.
    size 옵션: "1024x1024" (정사각), "1536x1024" (가로), "1024x1536" (세로)
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY가 설정되어 있지 않습니다. .env 파일을 확인하세요."
        )

    client = OpenAI(api_key=api_key)

    files = [open(p, "rb") for p in input_image_paths]
    try:
        result = client.images.edit(
            model="gpt-image-1",
            image=files,
            prompt=prompt,
            size=size,
            quality=quality,
            n=1,
        )
    finally:
        for f in files:
            f.close()

    image_base64 = result.data[0].b64_json
    image_bytes = base64.b64decode(image_base64)

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_bytes(image_bytes)

    print(f"이미지 편집 완료: {output_file}")
    return str(output_file)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("사용법: python generate_photo.py \"프롬프트\" 출력경로.png")
        print("     또는 (편집 모드): python generate_photo.py --edit \"프롬프트\" 출력경로.png 바탕사진.jpg [참고이미지.png ...]")
        sys.exit(1)

    if sys.argv[1] == "--edit":
        prompt_text = sys.argv[2]
        out_path = sys.argv[3]
        input_paths = sys.argv[4:]
        edit_photo_with_reference(prompt_text, input_paths, out_path, size="1024x1024")
    else:
        prompt_text = sys.argv[1]
        out_path = sys.argv[2]
        size_arg = sys.argv[3] if len(sys.argv) > 3 else "1536x1024"

        generate_photo(prompt_text, out_path, size=size_arg)