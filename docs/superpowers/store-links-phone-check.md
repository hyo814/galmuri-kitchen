# 쇼핑몰 링크 폰 확인표 (4단계 Task 9 Step 2)

쇼핑몰 6곳(쿠팡·네이버 쇼핑·컬리·이마트몰·롯데마트·G마켓) 모두 2026-09-17에 사용자가 폰(크롬·삼성 인터넷)으로 확인해 `낮은 가격순`이 적용됐습니다(`frontend/src/storeLinks.ts`의 `verified` 줄 참고). 홈플러스는 확인 결과 정렬 후보가 없어 목록에서 뺐습니다.
아래는 쇼핑몰 검색 주소가 바뀌는 등 다시 확인해야 할 때 쓰는 빈 작업표입니다. 확인 전에는 운영 화면의 쇼핑몰 시트가 쇼핑몰마다 정렬 칩 없이 `검색 결과` 링크 하나만 보여줘요(확인한 쇼핑몰만 정렬 칩, 개발 서버에서는 후보를 모두 보여줘요).

## 폰에서 여는 방법

- 폰 브라우저에서 이 파일을 열어요: `https://github.com/<계정>/<저장소>/blob/main/docs/superpowers/store-links-phone-check.md` (`<계정>/<저장소>`는 이 프로젝트 저장소로 바꿔주세요)
- PC에서 열어 폰으로 링크를 보내도 돼요.

## 확인하는 방법

1. 각 줄의 `열기`를 눌러요. **크롬과 삼성 인터넷 모두에서 되면 된 것**이에요.
2. 줄마다 세 가지를 봐요.
   - **검색어 유지**: 검색 결과가 그 검색어(`대파`, `두부 한 모`, `참기름`)로 떠요. `두부 한 모`는 띄어쓰기까지 그대로인지 봐요.
   - **정렬 적용**: 결과가 줄 이름대로 정렬돼 있어요(낮은 가격순 · 많이 산 순 · 새 상품순). `새 상품순`이 오래된 순으로 뜨면 안 된 거예요.
   - **앱에서도 유지**: 쇼핑몰 앱이 깔려 있어 앱으로 넘어가면, 앱에서도 검색어(와 정렬)가 그대로예요. 앱으로 안 넘어가면 이 칸은 넘어가도 돼요.
3. **안 된 줄만 채팅으로 보내주세요**(예: `쿠팡 · 낮은 가격순 — 정렬이 안 먹어요`). 안 보낸 줄은 된 걸로 볼게요. 한 브라우저에서만 안 되면 어느 쪽인지 같이 적어주세요.
4. 받은 내용으로 된 칸만 남기고 안 되는 정렬 칩은 숨기고, 검색까지 안 되는 쇼핑몰은 화면에서 빼요.

주소 목록은 `cd frontend && node scripts/check-store-links.mjs --checklist`로 다시 만들 수 있어요(`--print`는 같은 주소를 한 줄씩 보여줘요).

## 대파

| 쇼핑몰 · 정렬 | 주소 | 검색어 유지 | 정렬 적용 | 앱에서도 유지 | 메모 |
|---|---|---|---|---|---|
| 쿠팡 · 낮은 가격순 | [열기](https://www.coupang.com/np/search?q=%EB%8C%80%ED%8C%8C&sorter=salePriceAsc) | ☐ | ☐ | ☐ |  |
| 네이버 쇼핑 · 낮은 가격순 | [열기](https://search.shopping.naver.com/search/all?query=%EB%8C%80%ED%8C%8C&sort=price_asc) | ☐ | ☐ | ☐ |  |
| 컬리 · 낮은 가격순 | [열기](https://www.kurly.com/search?sword=%EB%8C%80%ED%8C%8C&sorted_type=2) | ☐ | ☐ | ☐ |  |
| 이마트몰 · 낮은 가격순 | [열기](https://emart.ssg.com/search.ssg?query=%EB%8C%80%ED%8C%8C&sort=prcasc) | ☐ | ☐ | ☐ |  |
| 롯데마트 · 낮은 가격순 | [열기](https://lottemartzetta.com/products/search?q=%EB%8C%80%ED%8C%8C&sortBy=pricePerAscending) | ☐ | ☐ | ☐ |  |
| G마켓 · 낮은 가격순 | [열기](https://www.gmarket.co.kr/n/search?keyword=%EB%8C%80%ED%8C%8C&f=sp:lp) | ☐ | ☐ | ☐ |  |

## 두부 한 모

| 쇼핑몰 · 정렬 | 주소 | 검색어 유지 | 정렬 적용 | 앱에서도 유지 | 메모 |
|---|---|---|---|---|---|
| 쿠팡 · 낮은 가격순 | [열기](https://www.coupang.com/np/search?q=%EB%91%90%EB%B6%80%20%ED%95%9C%20%EB%AA%A8&sorter=salePriceAsc) | ☐ | ☐ | ☐ |  |
| 네이버 쇼핑 · 낮은 가격순 | [열기](https://search.shopping.naver.com/search/all?query=%EB%91%90%EB%B6%80%20%ED%95%9C%20%EB%AA%A8&sort=price_asc) | ☐ | ☐ | ☐ |  |
| 컬리 · 낮은 가격순 | [열기](https://www.kurly.com/search?sword=%EB%91%90%EB%B6%80%20%ED%95%9C%20%EB%AA%A8&sorted_type=2) | ☐ | ☐ | ☐ |  |
| 이마트몰 · 낮은 가격순 | [열기](https://emart.ssg.com/search.ssg?query=%EB%91%90%EB%B6%80%20%ED%95%9C%20%EB%AA%A8&sort=prcasc) | ☐ | ☐ | ☐ |  |
| 롯데마트 · 낮은 가격순 | [열기](https://lottemartzetta.com/products/search?q=%EB%91%90%EB%B6%80%20%ED%95%9C%20%EB%AA%A8&sortBy=pricePerAscending) | ☐ | ☐ | ☐ |  |
| G마켓 · 낮은 가격순 | [열기](https://www.gmarket.co.kr/n/search?keyword=%EB%91%90%EB%B6%80%20%ED%95%9C%20%EB%AA%A8&f=sp:lp) | ☐ | ☐ | ☐ |  |

## 참기름

| 쇼핑몰 · 정렬 | 주소 | 검색어 유지 | 정렬 적용 | 앱에서도 유지 | 메모 |
|---|---|---|---|---|---|
| 쿠팡 · 낮은 가격순 | [열기](https://www.coupang.com/np/search?q=%EC%B0%B8%EA%B8%B0%EB%A6%84&sorter=salePriceAsc) | ☐ | ☐ | ☐ |  |
| 네이버 쇼핑 · 낮은 가격순 | [열기](https://search.shopping.naver.com/search/all?query=%EC%B0%B8%EA%B8%B0%EB%A6%84&sort=price_asc) | ☐ | ☐ | ☐ |  |
| 컬리 · 낮은 가격순 | [열기](https://www.kurly.com/search?sword=%EC%B0%B8%EA%B8%B0%EB%A6%84&sorted_type=2) | ☐ | ☐ | ☐ |  |
| 이마트몰 · 낮은 가격순 | [열기](https://emart.ssg.com/search.ssg?query=%EC%B0%B8%EA%B8%B0%EB%A6%84&sort=prcasc) | ☐ | ☐ | ☐ |  |
| 롯데마트 · 낮은 가격순 | [열기](https://lottemartzetta.com/products/search?q=%EC%B0%B8%EA%B8%B0%EB%A6%84&sortBy=pricePerAscending) | ☐ | ☐ | ☐ |  |
| G마켓 · 낮은 가격순 | [열기](https://www.gmarket.co.kr/n/search?keyword=%EC%B0%B8%EA%B8%B0%EB%A6%84&f=sp:lp) | ☐ | ☐ | ☐ |  |
