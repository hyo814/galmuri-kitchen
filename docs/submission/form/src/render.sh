#!/bin/sh
# 슬라이드 HTML을 1920×1080 PNG로 다시 렌더링해요. 스크린샷을 새로 찍은 뒤 실행: sh docs/submission/form/src/render.sh
set -e
cd "$(dirname "$0")"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
for f in [0-9]*.html; do
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=1 \
    --window-size=1920,1080 --screenshot="$PWD/../${f%.html}.png" "file://$PWD/$f" 2>/dev/null
done
# 대표 이미지 1200×630: 가운데 1920×1008을 잘라 축소
cp ../00-대표이미지.png ../00-대표이미지-1200x630.png
sips --cropToHeightWidth 1008 1920 ../00-대표이미지-1200x630.png >/dev/null
sips --resampleHeightWidth 630 1200 ../00-대표이미지-1200x630.png >/dev/null
ls -1 ../*.png
