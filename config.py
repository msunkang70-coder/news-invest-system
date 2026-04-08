"""시스템 설정 — 모든 설정값 중앙 관리"""
from __future__ import annotations

import os
from pathlib import Path

# .env 파일 자동 로드
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass  # python-dotenv 미설치 시 환경변수만 사용

# ─────────────────────────── 경로 ───────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_ROOT / "output"
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"

OUTPUT_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)
CACHE_DIR.mkdir(exist_ok=True)

# ─────────────────────────── API 키 ───────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# ─────────────────────────── 수집 설정 ───────────────────────────
REQUEST_TIMEOUT = 15
MAX_ARTICLES_PER_FEED = 30
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MarketImpactBot/2.0"

# ─────────────────────────── RSS 소스 ───────────────────────────
RSS_SOURCES_KR = [
    {"name": "연합뉴스 경제",   "url": "https://www.yna.co.kr/rss/economy.xml",               "region": "KR"},
    {"name": "한국경제",        "url": "https://www.hankyung.com/feed/all-news",               "region": "KR"},
    {"name": "매일경제",        "url": "https://www.mk.co.kr/rss/30100041/",                   "region": "KR"},
    {"name": "조선일보 경제",   "url": "https://www.chosun.com/arc/outboundfeeds/rss/category/economy/?outputType=xml", "region": "KR"},
    {"name": "SBS Biz",         "url": "https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=01&plink=RSSREADER",   "region": "KR"},
]

RSS_SOURCES_GLOBAL = [
    {"name": "Reuters World",      "url": "https://news.google.com/rss/search?q=site:reuters.com+business+OR+markets&hl=en-US&gl=US&ceid=US:en", "region": "GLOBAL"},
    {"name": "CNBC Top News",      "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114", "region": "GLOBAL"},
    {"name": "Investing.com News", "url": "https://www.investing.com/rss/news.rss",            "region": "GLOBAL"},
    {"name": "Bloomberg via GN",   "url": "https://news.google.com/rss/search?q=site:bloomberg.com+markets&hl=en-US&gl=US&ceid=US:en", "region": "GLOBAL"},
    {"name": "WSJ via GN",         "url": "https://news.google.com/rss/search?q=site:wsj.com+markets+economy&hl=en-US&gl=US&ceid=US:en", "region": "GLOBAL"},
    {"name": "FT via GN",          "url": "https://news.google.com/rss/search?q=site:ft.com+markets+economy&hl=en-US&gl=US&ceid=US:en", "region": "GLOBAL"},
]

# Google News RSS (fallback + 보조)
GOOGLE_NEWS_QUERIES = [
    {"name": "Google News - 반도체", "query": "semiconductor chip market stock",    "region": "GLOBAL"},
    {"name": "Google News - AI",     "query": "artificial intelligence stock market","region": "GLOBAL"},
    {"name": "Google News - 금리",   "query": "interest rate FOMC federal reserve", "region": "GLOBAL"},
    {"name": "Google News - 유가",   "query": "oil price crude OPEC",              "region": "GLOBAL"},
    {"name": "Google News - 한국경제","query": "South Korea economy export",         "region": "GLOBAL"},
    {"name": "Google News - 관세",   "query": "tariff trade war",                   "region": "GLOBAL"},
]

# ─────────────────────────── 키워드 필터 ───────────────────────────
KEYWORDS_STRONG = [
    # 매크로
    "금리", "기준금리", "CPI", "PPI", "FOMC", "연준", "Fed", "Federal Reserve",
    "인플레이션", "inflation", "디플레이션",
    # 지정학
    "전쟁", "war", "제재", "sanctions", "지정학", "geopolitical",
    # 에너지/원자재
    "유가", "oil price", "crude", "OPEC",
    "환율", "달러", "USD", "원달러", "dollar",
    "국채", "금리인상", "금리인하", "rate hike", "rate cut",
    # 반도체/AI
    "반도체", "semiconductor", "AI chip", "HBM", "NVIDIA", "엔비디아",
    "인공지능", "AI", "artificial intelligence",
    # 무역
    "수출", "export", "관세", "tariff", "trade war", "무역전쟁",
    # 실적
    "실적", "earnings", "가이던스", "guidance", "어닝서프라이즈",
    # 시장 이벤트
    "서킷브레이커", "circuit breaker", "블랙먼데이", "폭락", "급등",
    "crash", "surge", "plunge",
]

KEYWORDS_MEDIUM = [
    "산업 정책", "industrial policy", "규제", "regulation",
    "기업 투자", "capex", "설비투자",
    "공급망", "supply chain", "물류",
    "IPO", "M&A", "인수합병", "상장",
    "고용", "실업률", "unemployment", "nonfarm", "비농업",
    "GDP", "경제성장률", "PMI", "ISM",
    "배당", "자사주", "buyback",
]

KEYWORDS_WEAK = [
    "경제", "economy", "시장", "market",
    "투자", "investment", "주식", "stock",
]

# ─────────────────────────── 영향도 스코어링 가중치 ───────────────────────────
SCORE_WEIGHTS = {
    "macro": 3.0,       # 금리/전쟁/유가 등 매크로
    "industry": 2.0,    # 반도체/자동차 등 산업
    "market": 2.0,      # 환율/금리/지수
    "corporate": 1.5,   # 대형주 관련
    "keyword_tier": 1.5,  # 키워드 티어 보너스
}

IMPACT_THRESHOLD = 5  # 이 이상만 리포트에 포함

# ─────────────────────────── 종목 태깅 ───────────────────────────
STOCK_TAGS = {
    "삼성전자": ["삼성전자", "삼성 전자", "삼성반도체", "Samsung Electronics", "Samsung", "갤럭시", "파운드리", "DRAM", "이재용"],
    "SK하이닉스": ["SK하이닉스", "SK 하이닉스", "하이닉스", "SK Hynix", "Hynix", "HBM", "낸드", "NAND"],
    "현대차": ["현대차", "현대자동차", "현대 자동차", "Hyundai Motor", "Hyundai", "현대모비스", "기아", "기아차", "KIA"],
    "NVIDIA": ["NVIDIA", "Nvidia", "엔비디아", "Jensen Huang", "젠슨황", "GeForce", "CUDA"],
    "TSMC": ["TSMC", "대만반도체", "Taiwan Semi"],
    "테슬라": ["Tesla", "테슬라", "일론 머스크", "Elon Musk", "일론머스크"],
    "애플": ["Apple", "애플", "아이폰", "iPhone", "Tim Cook", "팀 쿡"],
    "마이크로소프트": ["Microsoft", "마이크로소프트", "MS Azure", "Copilot"],
    "구글": ["Google", "Alphabet", "구글", "알파벳", "Gemini"],
    "아마존": ["Amazon", "아마존", "AWS"],
    "메타": ["Meta", "메타", "Facebook", "페이스북", "Zuckerberg", "저커버그"],
    "LG에너지솔루션": ["LG에너지솔루션", "LG에너지", "LG Energy", "LGES"],
    "네이버": ["네이버", "NAVER", "Naver"],
    "카카오": ["카카오", "Kakao"],
}

# ─────────────────────────── LLM 설정 ───────────────────────────
GEMINI_MODEL = "gemini-2.0-flash"
LLM_TIMEOUT = 30
LLM_MAX_RETRIES = 3
LLM_DELAY_BETWEEN_CALLS = 4  # 초 — 무료 티어 rate limit 대응
LLM_BATCH_PAUSE = 10          # N건마다 추가 대기

# ─────────────────────────── 캐시 설정 ───────────────────────────
CACHE_TTL_HOURS = 24
TITLE_SIMILARITY_THRESHOLD = 0.7

# ─────────────────────────── 시간대 (KST) ───────────────────────────
TIMESLOTS_KST = {
    "프리마켓": (6, 0, 8, 59),      # 06:00 ~ 08:59
    "장중": (9, 0, 15, 30),          # 09:00 ~ 15:30
    "애프터마켓": (15, 31, 23, 59),  # 15:31 ~ 23:59
    # 00:00 ~ 05:59 → 글로벌
}
