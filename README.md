# PDF/이미지 표 추출 도구

PDF나 이미지에서 표를 자동으로 추출하여 CSV 파일로 변환하는 웹 애플리케이션입니다. Google의 Gemini AI를 활용하여 정확한 표 데이터 추출을 지원합니다.

## 주요 기능

- **PDF 및 이미지 지원**: PDF 파일 또는 다양한 이미지 형식(JPG, PNG, BMP, WEBP)에서 표 추출
- **다양한 표 유형 지원**: 재무제표, 손익계산서, 현금흐름표, 계약서 등 다양한 유형의 표 인식
- **고품질 데이터 추출**: Google Gemini AI를 활용한 정확한 표 데이터 추출
- **CSV 다운로드**: 추출된 데이터를 CSV 파일로 쉽게 다운로드
- **표 재구성 옵션**: 계약서와 같은 특정 형식의 표를 보기 좋게 재구성
- **개발자 모드**: 고급 사용자를 위한 커스텀 프롬프트 지원

## 설치 및 실행

### 요구사항

- Python 3.8 이상
- Google API 키 (Gemini 모델 사용을 위함)

### 로컬 설치

1. 저장소 클론
```bash
git clone https://github.com/your-username/pdf-image-table-extractor.git
cd pdf-image-table-extractor
```

2. 필요한 패키지 설치
```bash
pip install -r requirements.txt
```

3. 실행
```bash
streamlit run app.py
```

### Streamlit Cloud 배포

1. GitHub에 코드 푸시
2. [Streamlit Cloud](https://streamlit.io/cloud)에 로그인
3. 'New app' 클릭 후 저장소와 main 파일 선택
4. 비밀값으로 Google API 키 추가 (GEMINI_API_KEY)

## 사용 방법

1. Google API 키 입력
2. 파일 유형 선택 (PDF 또는 이미지)
3. 파일 업로드
4. "표 추출 시작" 버튼 클릭
5. 추출된 표 확인 및 CSV 다운로드

## 고급 설정

- **추출 품질**: '높음', '균형', '빠름' 중 선택하여 품질과 속도 조절
- **표 재구성**: 특정 형식의 표(예: 계약서)를 보기 좋게 재구성
- **개발자 모드**: 사용자 정의 프롬프트로 추출 과정 커스터마이징

## 참고 사항

- 표가 명확하고 깔끔할수록 더 정확한 결과를 얻을 수 있습니다.
- PDF 파일의 경우 텍스트 레이어가 있는 PDF가 더 좋은 결과를 제공합니다.
- 이미지 파일의 경우 고해상도 이미지가 더 정확한 추출을 가능하게 합니다.
- 인식 오류가 발생하면 이미지 해상도 개선, 다른 파일 형식 시도 등의 방법을 시도해보세요.

## 라이센스

MIT 라이센스에 따라 배포됩니다. 자세한 내용은 LICENSE 파일을 참조하세요.
