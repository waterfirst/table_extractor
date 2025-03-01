
import streamlit as st
import pandas as pd
import tempfile
import os
import base64
import json
import google.generativeai as genai
from google.api_core.exceptions import GoogleAPIError
import io
import time
import re
from datetime import datetime
from PIL import Image
import PyPDF2

# 페이지 설정
st.set_page_config(
    page_title="PDF/이미지 표 추출 도구",
    page_icon="📊",
    layout="centered",
    initial_sidebar_state="expanded"
)

# API 키 설정
def get_api_key():
    try:
        return st.secrets["gemini"]["api_key"]
    except:
        if "api_key" in st.session_state and st.session_state["api_key"]:
            return st.session_state["api_key"]
        return None

# Gemini API 설정
def setup_gemini_api(api_key):
    try:
        genai.configure(api_key=api_key)
        return True
    except Exception as e:
        st.error(f"Gemini API 설정 중 오류가 발생했습니다: {e}")
        return False

# 현재 날짜와 시간을 파일명에 적합한 형식으로 반환
def get_timestamp_filename():
    """현재 날짜와 시간을 'YYYY-MM-DD_HHMMSS' 형식으로 반환"""
    now = datetime.now()
    return now.strftime("%Y-%m-%d_%H%M%S")

# PDF 테이블 구조와 유사하게 데이터 재구성
def restructure_table_data(df):
    """
    Gemini가 추출한 단일 행 CSV 데이터를 PDF 테이블 구조와 유사하게 재구성
    
    Args:
        df (DataFrame): 원본 데이터프레임
    
    Returns:
        DataFrame: 재구성된 데이터프레임
    """
    try:
        # 데이터가 없는 경우 원본 반환
        if df.empty or len(df) == 0:
            return df
            
        # 첫 번째 행의 데이터만 사용 (일반적으로 단일 행으로 추출됨)
        if len(df) == 1:
            row_data = df.iloc[0]
        else:
            # 여러 행이 있는 경우 (드문 경우) 첫 행 사용
            row_data = df.iloc[0]
        
        # 새로운 데이터프레임 구조 정의
        # 상단 테이블 (기본 정보)
        header1 = ['호실', '계약자', '면적(㎡)', '분양대금']
        data1 = []
        
        # 행 1 (호실, 계약번호, 계약자, 면적)
        if '호실' in df.columns and '계약자' in df.columns:
            data1.append([
                row_data.get('호실', ''),
                row_data.get('계약자', ''),
                row_data.get('면적(㎡)', ''),
                row_data.get('분양대금', '')
            ])
        else:
            # 컬럼명이 다른 경우 처리
            columns = df.columns.tolist()
            if len(columns) >= 4:
                data1.append([row_data[columns[0]], row_data[columns[1]], 
                             row_data[columns[2]], row_data[columns[5]]])
            else:
                # 컬럼이 부족한 경우 빈 데이터 삽입
                data1.append(['', '', '', ''])
        
        top_table = pd.DataFrame(data1, columns=header1)
        
        # 하단 테이블 (납부 정보)
        header2 = ['구분', '납부할금액(연체료포함)', '납부금액', '납부일']
        data2 = []
        
        # 계약금
        data2.append(['계약금', 
                     row_data.get('납부할금액(연체료포함)', ''), 
                     row_data.get('납부금액', ''),
                     row_data.get('납부일', '')])
        
        # 중도금 1~4차
        for i in range(1, 5):
            data2.append([f'중도금 {i}차',
                         row_data.get(f'납부할금액(연체료포함).{i}', ''),
                         row_data.get(f'납부금액.{i}', ''),
                         row_data.get(f'납부일.{i}', '')])
        
        # 잔금
        data2.append(['잔금',
                     row_data.get('납부할금액(연체료포함).5', ''),
                     row_data.get('납부금액.5', ''),
                     row_data.get('납부일.5', '')])
        
        bottom_table = pd.DataFrame(data2, columns=header2)
        
        # 필요한 경우 두 테이블을 결합
        # 여기서는 별도로 반환하여 사용자가 선택할 수 있게 함
        return {
            'top_table': top_table,
            'bottom_table': bottom_table,
            'combined': pd.concat([top_table, pd.DataFrame([['---', '---', '---', '---']], columns=header1), bottom_table], ignore_index=True)
        }
        
    except Exception as e:
        print(f"테이블 재구성 중 오류: {e}")
        return df

# 이미지 처리 함수
def process_image_file(image_file):
    """
    업로드된 이미지 파일을 처리하여 바이트로 반환
    
    Args:
        image_file: Streamlit의 업로드된 이미지 파일
        
    Returns:
        bytes: 처리된 이미지의 바이트
    """
    try:
        # 이미지 파일 읽기
        image_bytes = io.BytesIO(image_file.getvalue())
        image = Image.open(image_bytes)
        
        # 이미지 크기 확인
        width, height = image.size
        
        # 이미지 최적화 및 품질 개선
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # 이미지가 너무 작은 경우 확대
        min_dimension = 1200  # 최소 권장 크기
        if width < min_dimension or height < min_dimension:
            scale_factor = max(min_dimension / width, min_dimension / height)
            new_width = int(width * scale_factor)
            new_height = int(height * scale_factor)
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            st.info(f"이미지 품질 개선을 위해 크기를 조정했습니다: {width}x{height} → {new_width}x{new_height}")
        
        # 이미지 선명도 개선 (필요한 경우)
        from PIL import ImageEnhance
        enhancer = ImageEnhance.Sharpness(image)
        image = enhancer.enhance(1.2)  # 약간의 선명도 향상
        
        # 대비 향상
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(1.1)  # 약간의 대비 향상
            
        # 고품질 바이트로 변환
        output_bytes = io.BytesIO()
        image.save(output_bytes, format='PNG', compress_level=0)  # 최대 품질
        output_bytes.seek(0)
        
        return output_bytes.getvalue()
        
    except Exception as e:
        st.error(f"이미지 처리 중 오류: {e}")
        return None

# PDF에서 첫 페이지만 추출
def extract_first_page_pdf(pdf_file):
    """PDF에서 첫 페이지만 추출하여 새 PDF로 반환"""
    try:
        # 입력 PDF 읽기
        pdf_bytes = io.BytesIO(pdf_file.getvalue())
        reader = PyPDF2.PdfReader(pdf_bytes)
        
        if len(reader.pages) == 0:
            st.error("PDF 파일이 비어있습니다.")
            return None
            
        # 새 PDF 생성
        writer = PyPDF2.PdfWriter()
        # 첫 페이지만 추가
        writer.add_page(reader.pages[0])
        
        # 새 PDF를 바이트로 저장
        output_bytes = io.BytesIO()
        writer.write(output_bytes)
        output_bytes.seek(0)
        
        return output_bytes.getvalue()
        
    except Exception as e:
        st.error(f"PDF 첫 페이지 추출 중 오류: {e}")
        return None


# 핵심 함수: 파일을 Gemini API에 직접 전송하여 표 추출
def extract_tables_from_file_directly(file_bytes, file_type, gemini_model, max_retries=3):
    """파일을 직접 Gemini API에 전송하여 표 추출"""
    try:
        # API 키 확인
        api_key = get_api_key()
        if not api_key:
            st.error("API 키가 설정되지 않았습니다.")
            return []
            
        # API 키 설정
        if not setup_gemini_api(api_key):
            st.error("Gemini API 설정에 실패했습니다.")
            return []
        
        # 고급 설정에 따른 모델 구성
        temperature = 0.0
        max_tokens = 30000
        
        if 'extraction_quality' in st.session_state:
            if st.session_state.extraction_quality == "빠름":
                temperature = 0.2
                max_tokens = 12000
            elif st.session_state.extraction_quality == "균형":
                temperature = 0.1
                max_tokens = 20000
            else:  # 높은 품질
                temperature = 0.0
                max_tokens = 30000
        
        # 파일 타입에 따라 프롬프트 및 MIME 타입 설정
        if file_type == "pdf":
            prompt = """
            이 PDF 문서에서 모든 표를 찾아 정확한 CSV 형식으로 변환해주세요. 
            PDF가 90도 회전되어 있더라도 알아서 인식하고 표의 내용을 정확히 추출해주세요.

            추출 시 다음 지침을 철저히 따라주세요:
            1. 문서에 있는 모든 표를 개별적으로 추출하세요. 이는 다음과 같은 모든 유형의 표를 포함합니다:
               - 재무제표/재무상태표/대차대조표
               - 손익계산서
               - 현금흐름표
               - 자본변동표
               - 주요 투자지표
               - 주석사항과 부가설명이 포함된 표
               - 그 외 모든 숫자나 데이터가 포함된 표

            2. 각 표의 구조와 형식을 정확하게 유지하세요:
               - 연도별 칼럼 구조 유지 (2016, 2017, 2018, 2019, 2020년 등 모든 연도 포함)
               - 금액 단위(백만원, 억원 등) 표시 포함
               - 모든 항목명(매출액, 영업이익, 자산총계 등)을 정확히 포함
               - 음수 값은 원래 형태로 유지(-기호 포함)
               - 비율(%) 값은 원래 형태로 유지(% 기호 포함 가능)
            
            3. 표 전체를 완전히 추출하세요:
               - 표의 모든 행과 열이 누락 없이 추출되어야 합니다
               - 표의 제목/헤더/부제목도 포함해야 합니다
               - 표 하단의 주석이나 출처 정보도 가능하면 포함하세요
            
            4. 각 표를 개별적으로 처리하여 "TABLE_START"로 시작하고 "TABLE_END"로 끝내세요.
            5. 빈 셀은 빈 문자열("")로 표시하세요.
            6. 표가 없으면 "NO_TABLES_FOUND"라고 응답하세요.

            응답은 CSV 형식의 텍스트만 제공하고, 다른 설명이나 분석은 포함하지 마세요.
            """
            mime_type = "application/pdf"
        else:  # 이미지 파일인 경우
            prompt = """
            이 이미지에서 모든 표를 찾아 정확한 CSV 형식으로 변환해주세요.
            이미지가 90도 회전되어 있더라도 알아서 인식하고 표의 내용을 정확히 추출해주세요.

            추출 시 다음 지침을 철저히 따라주세요:
            1. 이미지에 있는 모든 표를 개별적으로 추출하세요. 이는 다음과 같은 모든 유형의 표를 포함합니다:
               - 재무제표/재무상태표/대차대조표 (유동자산, 비유동자산, 자산총계, 부채, 자본 등)
               - 손익계산서 (매출액, 매출원가, 판매비와관리비, 영업이익, EBITDA 등)
               - 현금흐름표 (영업활동, 투자활동, 재무활동 현금흐름 등)
               - 자본변동표
               - 주요 투자지표 (성장성, 수익성, EPS, PER, ROE 등)
               - 그 외 모든 숫자나 데이터가 포함된 표
            
            2. 각 표의 구조와 형식을 정확하게 유지하세요:
               - 연도별 칼럼 구조 유지 (표에 있는 모든 연도의 데이터를 추출)
               - 모든 행과 열을 누락 없이 포함 (금액, 비율, 숫자값 등)
               - 표의 원래 구조를 최대한 그대로 유지
               - 음수 값은 "-" 기호를 포함하여 원래 형태로 유지
               - 괄호 안의 숫자(손실/마이너스 표시)도 음수로 적절히 변환
            
            3. 표 전체를 완전히 추출하세요:
               - 표 상단의 제목과 부제목도 가능하면 포함
               - 표 내의 모든 카테고리와 항목명을 정확하게 포함
               - 표 하단의 주석이나 출처 정보도 가능하면 포함
            
            4. 각 표마다 "TABLE_START"로 시작하고 "TABLE_END"로 끝내세요.
            5. 빈 셀은 빈 문자열("")로 처리하세요.
            6. 표가 없으면 "NO_TABLES_FOUND"라고 응답하세요.

            응답은 CSV 형식의 텍스트만 제공하고, 다른 설명이나 분석은 포함하지 마세요.
            이미지에 보이는 모든 표와 데이터를 완전하고 정확하게 추출하는 것이 가장 중요합니다.
            """
            # 이미지 파일 MIME 타입 설정
            if file_type.lower() in ["jpg", "jpeg"]:
                mime_type = "image/jpeg"
            elif file_type.lower() == "png":
                mime_type = "image/png"
            else:
                mime_type = f"image/{file_type.lower()}"
        
        # 개발자 모드에서 커스텀 프롬프트 사용
        if st.session_state.get('developer_mode', False) and st.session_state.get('custom_prompt'):
            prompt = st.session_state.get('custom_prompt')
            st.info("커스텀 프롬프트를 사용합니다.")
        
        # API 호출 로직
        for attempt in range(max_retries):
            try:
                with st.spinner(f"Gemini API로 표 추출 중... (시도 {attempt+1}/{max_retries})"):
                    model = genai.GenerativeModel(
                        gemini_model,
                        generation_config=genai.GenerationConfig(
                            temperature=temperature,  # 설정된 온도 사용
                            top_p=0.95,
                            max_output_tokens=max_tokens,  # 설정된 토큰 수 사용
                        )
                    )
                    
                    response = model.generate_content([
                        prompt, 
                        {
                            "mime_type": mime_type,
                            "data": file_bytes
                        }
                    ])
                    result = response.text
                    
                    # 디버깅 모드 출력 (옵션)
                    if st.session_state.get('developer_mode', False):
                        st.text_area("API 응답 원본", result, height=200)
                    
                    if "NO_TABLES_FOUND" in result:
                        return []
                    
                    # 결과 처리 코드 (CSV 파싱 등)
                    tables_data = []
                    table_pattern = r"TABLE_START\s*(.*?)\s*TABLE_END"
                    matches = re.findall(table_pattern, result, re.DOTALL)
                    
                    for table_idx, table_csv in enumerate(matches):
                        if table_csv.strip():
                            try:
                                # 불필요한 빈 공간 및 따옴표 정리
                                table_csv = re.sub(r'\s*"\s*,\s*', '",', table_csv)
                                table_csv = re.sub(r'\s*,\s*"\s*', ',"', table_csv)
                                
                                # CSV 파싱
                                table_data = pd.read_csv(
                                    io.StringIO(table_csv.strip()), 
                                    skipinitialspace=True,
                                    on_bad_lines='warn',
                                    quoting=1,  # QUOTE_ALL 모드 사용하여 따옴표 처리 개선
                                    dtype=str  # 모든 열을 문자열로 처리
                                )
                                
                                # 빈 열/행 제거
                                table_data = table_data.dropna(how='all', axis=0).dropna(how='all', axis=1)
                                
                                # 모든 열이 Unnamed인 경우 헤더 없이 처리
                                if all('Unnamed' in str(col) for col in table_data.columns):
                                    table_data.columns = [f'Column_{i}' for i in range(len(table_data.columns))]
                                
                                # 원본 데이터 저장
                                original_df = table_data.copy()
                                
                                # 결과에 추가 - 재구성이 불필요한 경우 원본 데이터를 바로 사용
                                tables_data.append({
                                    'index': table_idx,
                                    'df': original_df,
                                    'original_df': original_df  # 원본 데이터도 저장
                                })
                            except Exception as csv_error:
                                st.warning(f"표 {table_idx+1} CSV 파싱 오류: {csv_error}")
                                
                                # 파싱 오류 복구 시도
                                try:
                                    # 쉼표 분리 문제 해결 시도
                                    fixed_csv = re.sub(r'("[^"]*),([^"]*")', r'\1COMMA\2', table_csv)
                                    fixed_csv = fixed_csv.replace('COMMA', ',')
                                    
                                    table_data = pd.read_csv(
                                        io.StringIO(fixed_csv.strip()),
                                        skipinitialspace=True,
                                        on_bad_lines='skip',
                                        quoting=3,  # QUOTE_NONE
                                        dtype=str
                                    )
                                    
                                    if not table_data.empty:
                                        original_df = table_data.copy()
                                        tables_data.append({
                                            'index': table_idx,
                                            'df': original_df,
                                            'original_df': original_df,
                                            'recovery': True
                                        })
                                    else:
                                        raise Exception("복구된 데이터가 비어있습니다")
                                except:
                                    # 원본 CSV 텍스트 저장 (디버깅용)
                                    error_df = pd.DataFrame({'original_csv': [table_csv.strip()]})
                                    tables_data.append({
                                        'index': table_idx,
                                        'df': error_df,
                                        'error': True
                                    })
                    
                    return tables_data
                    
            except GoogleAPIError as e:
                if attempt < max_retries - 1:
                    delay = 2 * (attempt + 1)
                    st.warning(f"API 호출 중 오류 발생: {e}. {delay}초 후 재시도...")
                    time.sleep(delay)
                else:
                    st.error(f"Gemini API 호출 실패: {e}")
                    return []
            except Exception as e:
                st.error(f"표 추출 중 오류가 발생했습니다: {e}")
                return []
    except Exception as e:
        st.error(f"파일 처리 중 오류가 발생했습니다: {e}")
        return []

# 표가 계약 테이블 형식인지 확인하는 함수
def is_contract_table(df):
    """
    표가 계약 테이블 형식(호실, 계약자, 면적 등의 정보)인지 확인
    
    Args:
        df (DataFrame): 확인할 데이터프레임
    
    Returns:
        bool: 계약 테이블 형식이면 True, 아니면 False
    """
    if df is None or df.empty:
        return False
    
    # 계약 관련 키워드 검사
    contract_keywords = ['호실', '계약자', '면적', '분양대금', '납부', '계약금', '중도금', '잔금']
    
    # 컬럼명에 키워드가 포함되어 있는지 확인
    columns = [str(col).lower() for col in df.columns]
    column_match = any(keyword in ' '.join(columns).lower() for keyword in contract_keywords)
    
    # 데이터에 키워드가 포함되어 있는지 확인
    data_match = False
    if len(df) > 0:
        # 첫 10개 행만 검사 (성능상 이유)
        sample = df.head(10)
        for col in sample.columns:
            # 각 컬럼의 데이터를 문자열로 변환하여 검사
            col_data = ' '.join(sample[col].astype(str).tolist()).lower()
            if any(keyword in col_data for keyword in contract_keywords):
                data_match = True
                break
    
    # 표 형태 검사 (재무제표 같은 복잡한 표는 일반적으로 행이 많고 열이 많음)
    is_small_table = len(df) < 20 and len(df.columns) < 10
    
    # 계약 테이블로 판단하는 조건: 키워드가 포함되어 있고 작은 표여야 함
    return (column_match or data_match) and is_small_table

# 표 유형을 감지하는 함수
def detect_table_type(df):
    """
    표 유형을 감지하는 함수 (재무상태표, 손익계산서, 현금흐름표 등)
    
    Args:
        df (DataFrame): 감지할 데이터프레임
    
    Returns:
        str: 감지된 표 유형 ('재무상태표', '손익계산서', '현금흐름표', '기타')
    """
    if df is None or df.empty:
        return '알 수 없음'
    
    # 표 유형별 키워드
    table_type_keywords = {
        '재무상태표': ['재무상태표', '대차대조표', '자산', '부채', '자본', '유동자산', '비유동자산', '자산총계', '부채총계'],
        '손익계산서': ['손익계산서', '매출액', '매출원가', '매출총이익', '영업이익', '당기순이익', 'EBITDA', '판매비', '관리비'],
        '현금흐름표': ['현금흐름표', '영업활동', '투자활동', '재무활동', '현금흐름', '기초현금', '기말현금'],
        '투자지표': ['PER', 'ROA', 'ROE', 'EPS', 'BPS', '성장성', '수익성', '안정성', '주당순이익']
    }
    
    # 컬럼과 데이터를 하나의 문자열로 합침
    table_text = ' '.join([str(col) for col in df.columns])
    
    # 데이터에서 첫 20개 행만 샘플링하여 문자열로 합침
    if len(df) > 0:
        sample = df.head(20)
        for col in sample.columns:
            try:
                table_text += ' ' + ' '.join(sample[col].astype(str).tolist())
            except:
                pass
    
    table_text = table_text.lower()
    
    # 각 유형별 키워드 매칭 점수 계산
    type_scores = {}
    for table_type, keywords in table_type_keywords.items():
        score = sum(1 for keyword in keywords if keyword.lower() in table_text)
        type_scores[table_type] = score
    
    # 가장 높은 점수의 유형 선택
    max_score_type = max(type_scores.items(), key=lambda x: x[1])
    
    # 최소 점수 임계값 설정 (최소 2개 이상의 키워드가 매칭되어야 함)
    if max_score_type[1] >= 2:
        return max_score_type[0]
    else:
        return '기타'

# 표를 적절하게 가공하는 함수
def process_table_by_type(df, table_type):
    """
    표 유형에 따라 적절한 후처리를 수행하는 함수
    
    Args:
        df (DataFrame): 처리할 데이터프레임
        table_type (str): 표 유형 ('재무상태표', '손익계산서', '현금흐름표', '기타')
    
    Returns:
        DataFrame: 처리된 데이터프레임
    """
    if df is None or df.empty:
        return df
    
    # 모든 열과 행에서 공백 제거
    df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)
    
    # 빈 열과 빈 행 제거
    df = df.dropna(how='all', axis=0).dropna(how='all', axis=1)
    
    # 표 유형에 따른 처리
    if table_type in ['재무상태표', '손익계산서', '현금흐름표']:
        # 숫자 데이터 정리
        # 1) 천단위 구분자(쉼표) 제거
        # 2) 괄호로 표시된 음수를 "-" 기호로 변환
        for col in df.columns:
            if col != df.columns[0]:  # 첫 번째 열은 항목명이므로 제외
                df[col] = df[col].apply(lambda x: process_numeric_value(x) if pd.notna(x) else x)
    
    return df

# 숫자 값 처리 함수
def process_numeric_value(value):
    """
    숫자 값을 처리하는 함수
    
    Args:
        value: 처리할 값
    
    Returns:
        처리된 값
    """
    if not isinstance(value, str):
        return value
    
    # 천단위 구분자(쉼표) 제거
    value = value.replace(',', '')
    
    # 괄호로 표시된 음수를 "-" 기호로 변환
    if value.startswith('(') and value.endswith(')'):
        value = '-' + value[1:-1]
    
    return value



def main():
    st.title("PDF/이미지 표 추출 및 CSV 변환")
    
    # API 키 설정 로직 개선
    api_key = get_api_key()
    
    # 사이드바에 고급 설정 추가
    with st.sidebar:
        st.header("고급 설정")
        
        # 추출 품질 설정
        st.session_state.extraction_quality = st.radio(
            "추출 품질",
            options=["높음 (느림)", "균형", "빠름"],
            index=1  # 기본값은 '균형'
        )
        
        # 재구성 옵션 추가
        st.session_state.restructure_table = st.checkbox(
            "표 재구성",
            value=False,
            help="표 구조를 재구성합니다. 특정 형식(계약서 등)의 표에 유용하지만, 재무제표 같은 복잡한 표에는 사용하지 않는 것이 좋습니다."
        )
        
        # 개발자 모드 설정
        developer_mode = st.checkbox("개발자 모드")
        if developer_mode:
            st.session_state.developer_mode = True
            st.session_state.custom_prompt = st.text_area(
                "커스텀 프롬프트",
                value=st.session_state.get('custom_prompt', ''),
                height=200
            )
        else:
            st.session_state.developer_mode = False
    
    # API 키 입력 처리
    if not api_key:
        st.session_state["api_key"] = st.text_input("Google API 키를 입력하세요", type="password")
        api_key = st.session_state["api_key"]
        if not api_key:
            st.warning("API 키가 필요합니다.")
            st.stop()
    else:
        # API 키가 설정되었으면, Gemini API 초기화
        if not setup_gemini_api(api_key):
            st.error("API 키가 유효하지 않거나, Gemini API 초기화에 실패했습니다.")
            st.session_state.pop("api_key", None)  # 잘못된 API 키 제거
            st.stop()
        st.success("API 키가 설정되어 있습니다.")
    
    # 모델 선택
    gemini_model = st.selectbox("Gemini 모델", ["gemini-1.5-pro", "gemini-1.5-flash"])
    
    # 파일 타입 및 파일 업로더 설정
    file_type = st.radio("파일 타입 선택", ["PDF 파일", "이미지 파일"], horizontal=True)
    st.subheader(f"{file_type} 업로드")
    if file_type == "PDF 파일":
        uploaded_file = st.file_uploader("PDF 파일을 업로드하세요", type="pdf")
        file_format = "pdf"
    else:
        uploaded_file = st.file_uploader("이미지 파일을 업로드하세요", type=["jpg", "jpeg", "png", "bmp", "webp"])
        if uploaded_file is not None:
            file_format = uploaded_file.name.split('.')[-1].lower()
    
    if uploaded_file is not None:
        st.write({
            "파일명": uploaded_file.name,
            "파일크기": f"{uploaded_file.size / 1024:.1f} KB",
            "파일타입": file_type
        })
        if file_type == "이미지 파일":
            st.image(uploaded_file, caption="업로드된 이미지", use_column_width=True)
        
        file_name = os.path.splitext(uploaded_file.name)[0]
        
        # 표 추출 결과를 저장할 변수를 미리 초기화하여 UnboundLocalError를 방지합니다.
        tables = []
        
        if st.button("표 추출 시작", type="primary"):
            with st.spinner(f"{file_type}에서 표를 추출하는 중입니다..."):
                # 파일 처리: PDF는 첫 페이지, 이미지의 경우 필요한 이미지 전처리 적용
                if file_type == "PDF 파일":
                    processed_file = extract_first_page_pdf(uploaded_file)
                else:
                    processed_file = process_image_file(uploaded_file)
                    
                if processed_file is None:
                    st.error(f"{file_type} 처리에 실패했습니다.")
                    st.stop()
                
                # Gemini API를 통해 표 추출
                tables = extract_tables_from_file_directly(processed_file, file_format, gemini_model)
            
            timestamp = get_timestamp_filename()
            
            # 추출된 표가 하나 이상인 경우 처리
            if tables:
                st.success(f"{len(tables)}개의 표를 찾았습니다.")
                if len(tables) > 1:
                    tabs = st.tabs([f"표 {i+1}" for i in range(len(tables))])
                    for tab_idx, tab in enumerate(tabs):
                        with tab:
                            table_data = next((t for t in tables if t['index'] == tab_idx), None)
                            if table_data:
                                df = table_data['df']
                                # 파싱 오류가 발생한 경우
                                if table_data.get('error', False):
                                    st.warning("이 표는 파싱 오류가 발생했습니다. 원본 CSV 데이터를 표시합니다.")
                                    st.text_area("원본 CSV", df.get('original_csv', ''), height=200)
                                else:
                                    # 표 재구성 옵션이 켜져 있고, 표가 일정 형식을 가진 경우에만 재구성
                                    should_restructure = st.session_state.get('restructure_table', False)
                                    
                                    if should_restructure and is_contract_table(df):
                                        restructured_data = restructure_table_data(df)
                                        if isinstance(restructured_data, dict) and 'top_table' in restructured_data:
                                            st.subheader("재구성된 데이터")
                                            st.dataframe(restructured_data['top_table'], use_container_width=True)
                                            st.dataframe(restructured_data['bottom_table'], use_container_width=True)
                                            # 재구성된 데이터로 업데이트
                                            df = restructured_data
                                        else:
                                            st.subheader("원본 데이터 (재구성 실패)")
                                            st.dataframe(df, use_container_width=True)
                                    else:
                                        st.subheader("원본 데이터")
                                        st.dataframe(df, use_container_width=True)
                                
                                # 다운로드 버튼 처리 (각 탭 별로 처리)
                                csv_filename = f"{file_name}_{timestamp}_table_{tab_idx+1}.csv"
                                if isinstance(df, dict) and 'combined' in df:
                                    csv = df['combined'].to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
                                else:
                                    csv = df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
                                
                                st.download_button(
                                    label="CSV로 다운로드",
                                    data=csv,
                                    file_name=csv_filename,
                                    mime='text/csv'
                                )
                else:
                    # 단일 표인 경우
                    st.subheader("추출된 표")
                    df = tables[0]['df']
                    if tables[0].get('error', False):
                        st.warning("이 표는 파싱 오류가 발생했습니다. 원본 CSV 데이터를 표시합니다.")
                        st.text_area("원본 CSV", df.get('original_csv', ''), height=200)
                    else:
                        # 표 재구성 옵션이 켜져 있고, 표가 일정 형식을 가진 경우에만 재구성
                        should_restructure = st.session_state.get('restructure_table', False)
                        
                        if should_restructure and is_contract_table(df):
                            restructured_data = restructure_table_data(df)
                            if isinstance(restructured_data, dict) and 'top_table' in restructured_data:
                                st.subheader("재구성된 데이터")
                                st.dataframe(restructured_data['top_table'], use_container_width=True)
                                st.dataframe(restructured_data['bottom_table'], use_container_width=True)
                                # 재구성된 데이터로 업데이트
                                df = restructured_data
                            else:
                                st.subheader("원본 데이터 (재구성 실패)")
                                st.dataframe(df, use_container_width=True)
                        else:
                            st.subheader("원본 데이터")
                            st.dataframe(df, use_container_width=True)
                    
                    csv_filename = f"{file_name}_{timestamp}_table_1.csv"
                    if isinstance(df, dict) and 'combined' in df:
                        csv = df['combined'].to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
                    else:
                        csv = df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
                    
                    st.download_button(
                        label="CSV로 다운로드",
                        data=csv,
                        file_name=csv_filename,
                        mime='text/csv'
                    )
            else:
                st.warning(f"{file_type}에서 표를 찾을 수 없습니다.")
                if file_type == "PDF 파일":
                    st.info("""
                    다음을 시도해보세요:
                    1. PDF가 텍스트 레이어를 포함하고 있는지 확인하세요 (스캔된 문서는 OCR이 필요할 수 있습니다).
                    2. 표가 실제로 표 형식인지 확인하세요.
                    3. PDF 파일 크기를 줄이거나 해상도를 높여보세요.
                    """)
                else:
                    st.info("""
                    다음을 시도해보세요:
                    1. 이미지 해상도가 충분히 높은지 확인하세요.
                    2. 이미지가 흐릿하거나 왜곡되지 않았는지 확인하세요.
                    3. 표가 명확하게 보이는지 확인하세요.
                    4. 다른 형식으로 변환해서 시도해보세요.
                    """)
    else:
        st.info("업로드할 파일을 선택하세요.")

       
if __name__ == "__main__":
    main()
    