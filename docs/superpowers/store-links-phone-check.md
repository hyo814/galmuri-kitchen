# 쇼핑몰 링크 폰 확인표 (4단계 Task 9 Step 2)

아직 **아무 칸도 확인되지 않았어요.** 아래 주소는 기억에 기대 적은 후보라서, 폰에서 직접 열어 봐야 화면에 내보낼 수 있어요.
확인 전에는 운영 화면의 쇼핑몰 시트가 `쇼핑몰 링크를 준비하고 있어요`만 보여줘요(개발 서버에서는 후보를 모두 보여줘요).

## 확인하는 방법

1. 갤럭시 S22 Ultra에서 이 파일을 열고, 각 줄의 `열기`를 눌러요. **크롬과 삼성 인터넷 둘 다** 확인해요.
2. 줄마다 세 가지를 봐요. 둘 다 통과하면 `☐`를 `☑`로 바꾸고, 한쪽만 되면 `메모`에 어느 브라우저에서 안 됐는지 적어주세요.
   - **검색어 유지**: 검색 결과가 그 검색어(`대파`, `두부 한 모`, `참기름`)로 떠요. `두부 한 모`는 띄어쓰기까지 그대로인지 봐요.
   - **정렬 적용**: 결과가 줄 이름대로 정렬돼 있어요(낮은 가격순 · 많이 산 순 · 새 상품순). `새 상품순`이 오래된 순으로 뜨면 안 된 걸로 적어주세요.
   - **앱에서도 유지**: 쇼핑몰 앱이 깔려 있어 앱으로 넘어가면, 앱에서도 검색어(와 정렬)가 그대로예요. 앱으로 안 넘어가면 `메모`에 `앱 전환 없음`이라고 적어주세요.
3. `정렬 후보 없음` 줄(컬리 · 홈플러스 · 롯데마트)은 검색어만 확인하고, 쇼핑몰 화면에서 정렬을 직접 바꾼 뒤 **주소창 주소를 복사해 `메모`에 붙여 주세요.** 정렬을 바꿔도 주소가 안 바뀌면 `주소 안 바뀜`이라고 적어주세요.
4. 다 끝나면 이 파일을 알려주세요. 통과한 칸만 남기고 안 되는 정렬 칩은 숨기고, 검색까지 안 되는 쇼핑몰은 화면에서 빼요.

주소 목록은 `cd frontend && node scripts/check-store-links.mjs --checklist`로 다시 만들 수 있어요(`--print`는 같은 주소를 한 줄씩 보여줘요).

## 대파

| 쇼핑몰 · 정렬 | 주소 | 검색어 유지 | 정렬 적용 | 앱에서도 유지 | 메모 |
|---|---|---|---|---|---|
| 쿠팡 · 낮은 가격순 | [열기](https://www.coupang.com/np/search?q=%EB%8C%80%ED%8C%8C&sorter=salePriceAsc) | ☐ | ☐ | ☐ |  |
| 쿠팡 · 많이 산 순 | [열기](https://www.coupang.com/np/search?q=%EB%8C%80%ED%8C%8C&sorter=saleCountDesc) | ☐ | ☐ | ☐ |  |
| 쿠팡 · 새 상품순 | [열기](https://www.coupang.com/np/search?q=%EB%8C%80%ED%8C%8C&sorter=latestAsc) | ☐ | ☐ | ☐ |  |
| 네이버 쇼핑 · 낮은 가격순 | [열기](https://search.shopping.naver.com/search/all?query=%EB%8C%80%ED%8C%8C&sort=price_asc) | ☐ | ☐ | ☐ |  |
| 네이버 쇼핑 · 새 상품순 | [열기](https://search.shopping.naver.com/search/all?query=%EB%8C%80%ED%8C%8C&sort=date) | ☐ | ☐ | ☐ |  |
| 컬리 · 검색 결과 | [열기](https://www.kurly.com/search?sword=%EB%8C%80%ED%8C%8C) | ☐ | 정렬 후보 없음 | ☐ |  |
| 이마트몰 · 낮은 가격순 | [열기](https://emart.ssg.com/search.ssg?query=%EB%8C%80%ED%8C%8C&sort=prcasc) | ☐ | ☐ | ☐ |  |
| 이마트몰 · 많이 산 순 | [열기](https://emart.ssg.com/search.ssg?query=%EB%8C%80%ED%8C%8C&sort=sale) | ☐ | ☐ | ☐ |  |
| 이마트몰 · 새 상품순 | [열기](https://emart.ssg.com/search.ssg?query=%EB%8C%80%ED%8C%8C&sort=regdt) | ☐ | ☐ | ☐ |  |
| 홈플러스 · 검색 결과 | [열기](https://front.homeplus.co.kr/search?entry=direct&keyword=%EB%8C%80%ED%8C%8C) | ☐ | 정렬 후보 없음 | ☐ |  |
| 롯데마트 · 검색 결과 | [열기](https://www.lotteon.com/search/search/search.ecn?render=search&platform=pc&q=%EB%8C%80%ED%8C%8C&mallId=4) | ☐ | 정렬 후보 없음 | ☐ |  |
| G마켓 · 낮은 가격순 | [열기](https://www.gmarket.co.kr/n/search?keyword=%EB%8C%80%ED%8C%8C&s=1) | ☐ | ☐ | ☐ |  |
| G마켓 · 많이 산 순 | [열기](https://www.gmarket.co.kr/n/search?keyword=%EB%8C%80%ED%8C%8C&s=8) | ☐ | ☐ | ☐ |  |
| G마켓 · 새 상품순 | [열기](https://www.gmarket.co.kr/n/search?keyword=%EB%8C%80%ED%8C%8C&s=3) | ☐ | ☐ | ☐ |  |

## 두부 한 모

| 쇼핑몰 · 정렬 | 주소 | 검색어 유지 | 정렬 적용 | 앱에서도 유지 | 메모 |
|---|---|---|---|---|---|
| 쿠팡 · 낮은 가격순 | [열기](https://www.coupang.com/np/search?q=%EB%91%90%EB%B6%80%20%ED%95%9C%20%EB%AA%A8&sorter=salePriceAsc) | ☐ | ☐ | ☐ |  |
| 쿠팡 · 많이 산 순 | [열기](https://www.coupang.com/np/search?q=%EB%91%90%EB%B6%80%20%ED%95%9C%20%EB%AA%A8&sorter=saleCountDesc) | ☐ | ☐ | ☐ |  |
| 쿠팡 · 새 상품순 | [열기](https://www.coupang.com/np/search?q=%EB%91%90%EB%B6%80%20%ED%95%9C%20%EB%AA%A8&sorter=latestAsc) | ☐ | ☐ | ☐ |  |
| 네이버 쇼핑 · 낮은 가격순 | [열기](https://search.shopping.naver.com/search/all?query=%EB%91%90%EB%B6%80%20%ED%95%9C%20%EB%AA%A8&sort=price_asc) | ☐ | ☐ | ☐ |  |
| 네이버 쇼핑 · 새 상품순 | [열기](https://search.shopping.naver.com/search/all?query=%EB%91%90%EB%B6%80%20%ED%95%9C%20%EB%AA%A8&sort=date) | ☐ | ☐ | ☐ |  |
| 컬리 · 검색 결과 | [열기](https://www.kurly.com/search?sword=%EB%91%90%EB%B6%80%20%ED%95%9C%20%EB%AA%A8) | ☐ | 정렬 후보 없음 | ☐ |  |
| 이마트몰 · 낮은 가격순 | [열기](https://emart.ssg.com/search.ssg?query=%EB%91%90%EB%B6%80%20%ED%95%9C%20%EB%AA%A8&sort=prcasc) | ☐ | ☐ | ☐ |  |
| 이마트몰 · 많이 산 순 | [열기](https://emart.ssg.com/search.ssg?query=%EB%91%90%EB%B6%80%20%ED%95%9C%20%EB%AA%A8&sort=sale) | ☐ | ☐ | ☐ |  |
| 이마트몰 · 새 상품순 | [열기](https://emart.ssg.com/search.ssg?query=%EB%91%90%EB%B6%80%20%ED%95%9C%20%EB%AA%A8&sort=regdt) | ☐ | ☐ | ☐ |  |
| 홈플러스 · 검색 결과 | [열기](https://front.homeplus.co.kr/search?entry=direct&keyword=%EB%91%90%EB%B6%80%20%ED%95%9C%20%EB%AA%A8) | ☐ | 정렬 후보 없음 | ☐ |  |
| 롯데마트 · 검색 결과 | [열기](https://www.lotteon.com/search/search/search.ecn?render=search&platform=pc&q=%EB%91%90%EB%B6%80%20%ED%95%9C%20%EB%AA%A8&mallId=4) | ☐ | 정렬 후보 없음 | ☐ |  |
| G마켓 · 낮은 가격순 | [열기](https://www.gmarket.co.kr/n/search?keyword=%EB%91%90%EB%B6%80%20%ED%95%9C%20%EB%AA%A8&s=1) | ☐ | ☐ | ☐ |  |
| G마켓 · 많이 산 순 | [열기](https://www.gmarket.co.kr/n/search?keyword=%EB%91%90%EB%B6%80%20%ED%95%9C%20%EB%AA%A8&s=8) | ☐ | ☐ | ☐ |  |
| G마켓 · 새 상품순 | [열기](https://www.gmarket.co.kr/n/search?keyword=%EB%91%90%EB%B6%80%20%ED%95%9C%20%EB%AA%A8&s=3) | ☐ | ☐ | ☐ |  |

## 참기름

| 쇼핑몰 · 정렬 | 주소 | 검색어 유지 | 정렬 적용 | 앱에서도 유지 | 메모 |
|---|---|---|---|---|---|
| 쿠팡 · 낮은 가격순 | [열기](https://www.coupang.com/np/search?q=%EC%B0%B8%EA%B8%B0%EB%A6%84&sorter=salePriceAsc) | ☐ | ☐ | ☐ |  |
| 쿠팡 · 많이 산 순 | [열기](https://www.coupang.com/np/search?q=%EC%B0%B8%EA%B8%B0%EB%A6%84&sorter=saleCountDesc) | ☐ | ☐ | ☐ |  |
| 쿠팡 · 새 상품순 | [열기](https://www.coupang.com/np/search?q=%EC%B0%B8%EA%B8%B0%EB%A6%84&sorter=latestAsc) | ☐ | ☐ | ☐ |  |
| 네이버 쇼핑 · 낮은 가격순 | [열기](https://search.shopping.naver.com/search/all?query=%EC%B0%B8%EA%B8%B0%EB%A6%84&sort=price_asc) | ☐ | ☐ | ☐ |  |
| 네이버 쇼핑 · 새 상품순 | [열기](https://search.shopping.naver.com/search/all?query=%EC%B0%B8%EA%B8%B0%EB%A6%84&sort=date) | ☐ | ☐ | ☐ |  |
| 컬리 · 검색 결과 | [열기](https://www.kurly.com/search?sword=%EC%B0%B8%EA%B8%B0%EB%A6%84) | ☐ | 정렬 후보 없음 | ☐ |  |
| 이마트몰 · 낮은 가격순 | [열기](https://emart.ssg.com/search.ssg?query=%EC%B0%B8%EA%B8%B0%EB%A6%84&sort=prcasc) | ☐ | ☐ | ☐ |  |
| 이마트몰 · 많이 산 순 | [열기](https://emart.ssg.com/search.ssg?query=%EC%B0%B8%EA%B8%B0%EB%A6%84&sort=sale) | ☐ | ☐ | ☐ |  |
| 이마트몰 · 새 상품순 | [열기](https://emart.ssg.com/search.ssg?query=%EC%B0%B8%EA%B8%B0%EB%A6%84&sort=regdt) | ☐ | ☐ | ☐ |  |
| 홈플러스 · 검색 결과 | [열기](https://front.homeplus.co.kr/search?entry=direct&keyword=%EC%B0%B8%EA%B8%B0%EB%A6%84) | ☐ | 정렬 후보 없음 | ☐ |  |
| 롯데마트 · 검색 결과 | [열기](https://www.lotteon.com/search/search/search.ecn?render=search&platform=pc&q=%EC%B0%B8%EA%B8%B0%EB%A6%84&mallId=4) | ☐ | 정렬 후보 없음 | ☐ |  |
| G마켓 · 낮은 가격순 | [열기](https://www.gmarket.co.kr/n/search?keyword=%EC%B0%B8%EA%B8%B0%EB%A6%84&s=1) | ☐ | ☐ | ☐ |  |
| G마켓 · 많이 산 순 | [열기](https://www.gmarket.co.kr/n/search?keyword=%EC%B0%B8%EA%B8%B0%EB%A6%84&s=8) | ☐ | ☐ | ☐ |  |
| G마켓 · 새 상품순 | [열기](https://www.gmarket.co.kr/n/search?keyword=%EC%B0%B8%EA%B8%B0%EB%A6%84&s=3) | ☐ | ☐ | ☐ |  |
