"""NIAS v2.0 — 중앙 설정 모듈

모든 소스, 키워드, 임계값, API 키를 중앙 관리.
코드 수정 없이 config만 변경하여 동작 조정 가능.
"""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

# ─────────────────────────── 경로 ───────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
OUTPUT_DIR = PROJECT_ROOT / "output"
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"

for d in (OUTPUT_DIR, DATA_DIR, CACHE_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ─────────────────────────── API 키 ───────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
DART_API_KEY = os.environ.get("DART_API_KEY", "")
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
BOK_API_KEY = os.environ.get("BOK_API_KEY", "")
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
ALERT_EMAIL_TO = os.environ.get("ALERT_EMAIL_TO", "")
KIS_APP_KEY = os.environ.get("KIS_APP_KEY", "")
KIS_APP_SECRET = os.environ.get("KIS_APP_SECRET", "")

# ─────────────────────────── 수집 설정 ───────────────────────────
REQUEST_TIMEOUT = 15
MAX_ARTICLES_PER_FEED = 30
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NIAS/2.0"

# ─────────────────────────── RSS 소스 ───────────────────────────
RSS_SOURCES_KR = [
    {"name": "연합뉴스 경제", "url": "https://www.yna.co.kr/rss/economy.xml", "region": "KR"},
    {"name": "한국경제", "url": "https://www.hankyung.com/feed/all-news", "region": "KR"},
    {"name": "매일경제", "url": "https://www.mk.co.kr/rss/30100041/", "region": "KR"},
    {"name": "조선일보 경제", "url": "https://www.chosun.com/arc/outboundfeeds/rss/category/economy/?outputType=xml", "region": "KR"},
    {"name": "SBS Biz", "url": "https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=01&plink=RSSREADER", "region": "KR"},
]

RSS_SOURCES_GLOBAL = [
    {"name": "Reuters World", "url": "https://news.google.com/rss/search?q=site:reuters.com+business+OR+markets&hl=en-US&gl=US&ceid=US:en", "region": "GLOBAL"},
    {"name": "CNBC Top News", "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114", "region": "GLOBAL"},
    {"name": "Investing.com", "url": "https://www.investing.com/rss/news.rss", "region": "GLOBAL"},
    {"name": "Bloomberg via GN", "url": "https://news.google.com/rss/search?q=site:bloomberg.com+markets&hl=en-US&gl=US&ceid=US:en", "region": "GLOBAL"},
    {"name": "WSJ via GN", "url": "https://news.google.com/rss/search?q=site:wsj.com+markets+economy&hl=en-US&gl=US&ceid=US:en", "region": "GLOBAL"},
    {"name": "FT via GN", "url": "https://news.google.com/rss/search?q=site:ft.com+markets+economy&hl=en-US&gl=US&ceid=US:en", "region": "GLOBAL"},
]

RSS_SOURCES_GEOPOLITICAL = [
    {"name": "Defense One", "url": "https://www.defenseone.com/rss/", "region": "GLOBAL"},
    {"name": "War on the Rocks", "url": "https://warontherocks.com/feed/", "region": "GLOBAL"},
    {"name": "The Diplomat", "url": "https://thediplomat.com/feed/", "region": "GLOBAL"},
    {"name": "38 North", "url": "https://www.38north.org/feed/", "region": "GLOBAL"},
]

GOOGLE_NEWS_QUERIES = [
    {"name": "GN - 반도체", "query": "semiconductor chip market stock", "region": "GLOBAL"},
    {"name": "GN - AI", "query": "artificial intelligence stock market", "region": "GLOBAL"},
    {"name": "GN - 금리", "query": "interest rate FOMC federal reserve", "region": "GLOBAL"},
    {"name": "GN - 유가", "query": "oil price crude OPEC", "region": "GLOBAL"},
    {"name": "GN - 한국경제", "query": "South Korea economy export", "region": "GLOBAL"},
    {"name": "GN - 관세", "query": "tariff trade war", "region": "GLOBAL"},
]

GOOGLE_NEWS_QUERIES_GEOPOLITICAL = [
    {"name": "GN - 전쟁/분쟁", "query": "war conflict military escalation", "region": "GLOBAL"},
    {"name": "GN - 제재", "query": "sanctions embargo geopolitical risk", "region": "GLOBAL"},
    {"name": "GN - 대만/중국", "query": "Taiwan strait China military", "region": "GLOBAL"},
]

# 종목/섹터별 Google News (한국어) — RSS 누락 보완
GOOGLE_NEWS_QUERIES_KR = [
    {"name": "GN-KR 삼성전자", "url": "https://news.google.com/rss/search?q=삼성전자+실적+반도체&hl=ko&gl=KR&ceid=KR:ko", "region": "KR"},
    {"name": "GN-KR SK하이닉스", "url": "https://news.google.com/rss/search?q=SK하이닉스+HBM+실적&hl=ko&gl=KR&ceid=KR:ko", "region": "KR"},
    {"name": "GN-KR 코스피", "url": "https://news.google.com/rss/search?q=코스피+증시+주식시장&hl=ko&gl=KR&ceid=KR:ko", "region": "KR"},
    {"name": "GN-KR 금리환율", "url": "https://news.google.com/rss/search?q=기준금리+환율+원달러&hl=ko&gl=KR&ceid=KR:ko", "region": "KR"},
    {"name": "GN-KR 유가에너지", "url": "https://news.google.com/rss/search?q=유가+에너지+OPEC&hl=ko&gl=KR&ceid=KR:ko", "region": "KR"},
]

# ─────────────────────────── 키워드 필터 ───────────────────────────
KEYWORDS_STRONG = [
    # 매크로
    "금리", "기준금리", "CPI", "PPI", "FOMC", "연준", "Fed", "Federal Reserve",
    "인플레이션", "inflation", "디플레이션",
    # 지정학
    "전쟁", "war", "제재", "sanctions", "지정학", "geopolitical",
    "에스컬레이션", "escalation", "군사적 충돌",
    "봉쇄", "blockade", "핵실험", "nuclear test",
    "ICBM", "미사일 발사", "missile launch",
    "NATO", "나토", "유엔 안보리", "UN Security Council",
    "계엄령", "martial law", "쿠데타", "coup",
    "대만해협", "Taiwan strait",
    "호르무즈해협", "Strait of Hormuz",
    # 시장지표
    "VIX", "공포지수", "변동성지수", "VKOSPI",
    "DXY", "달러인덱스", "dollar index",
    "야간선물", "night futures", "코스피200선물",
    "국채수익률", "treasury yield", "10년물", "2년물",
    "수익률 역전", "yield curve inversion",
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
    "실적", "earnings", "가이던스", "guidance", "어닝서프라���즈",
    # 위기
    "서킷브레이커", "circuit breaker", "블랙먼데이", "폭락", "급등",
    "crash", "surge", "plunge",
    "디폴트", "default", "채무불이행",
    "뱅크런", "bank run", "시스템 리스크",
    "경기침체", "recession", "스태그플레이션", "stagflation",
]

KEYWORDS_MEDIUM = [
    "산업 정책", "industrial policy", "규제", "regulation",
    "기업 투자", "capex", "설비투자",
    "공급망", "supply chain", "물류",
    "IPO", "M&A", "인수합병", "상장",
    "고용", "실업률", "unemployment", "nonfarm", "비농업",
    "GDP", "경제성장률", "PMI", "ISM",
    "배당", "자사주", "buyback",
    "양적긴축", "QT", "양적완화", "QE",
    "신용등급", "credit rating",
    "Fear and Greed", "공포탐욕지수",
]

KEYWORDS_WEAK = [
    "경제", "economy", "시장", "market",
    "투자", "investment", "주식", "stock",
]

# ─────────────────────────── 종목 태깅 ───────────────────────────
STOCK_TAGS = {
    "삼성전자": ["삼성전자", "Samsung Electronics", "Samsung", "갤럭시", "파운드리", "DRAM", "이재용"],
    "SK하이닉스": ["SK하이닉스", "SK Hynix", "Hynix", "HBM", "낸드", "NAND"],
    "현대차": ["현대차", "현대자동차", "Hyundai Motor", "Hyundai", "기아", "KIA"],
    "NVIDIA": ["NVIDIA", "Nvidia", "엔비디아", "젠슨황", "GeForce", "CUDA"],
    "TSMC": ["TSMC", "대만반도체", "Taiwan Semi"],
    "테슬라": ["Tesla", "테슬라", "일론 머스크", "Elon Musk"],
    "애플": ["Apple", "애플", "아이폰", "iPhone", "Tim Cook"],
    "마이크로소프트": ["Microsoft", "마이크로소프트", "MS Azure", "Copilot"],
    "구글": ["Google", "Alphabet", "구글", "알파벳", "Gemini"],
    "아마존": ["Amazon", "아마존", "AWS"],
    "메타": ["Meta", "메타", "Facebook", "Zuckerberg"],
    "LG에너지솔루션": ["LG에너지솔루션", "LG에너지", "LG Energy", "LGES"],
    "네이버": ["네이버", "NAVER", "Naver"],
    "카카오": ["카카오", "Kakao"],
}

# ─────────────────────────── 시장지표 임계값 ───────────────────────────
INDICATOR_THRESHOLDS = {
    "^VIX": {
        "name": "VIX 공포지수",
        "absolute": [(25, "WARNING", "시장 불안 구간"), (30, "CRITICAL", "공포 구간"), (40, "EXTREME", "패닉 구간")],
        "change_pct": 15,
    },
    "DX-Y.NYB": {
        "name": "달러인덱스 (DXY)",
        "absolute": [(105, "WARNING", "강달러 구간"), (107, "CRITICAL", "달러 과열")],
        "change_pct": 1.0,
    },
    "CL=F": {
        "name": "WTI 원유",
        "absolute": [(100, "WARNING", "유가 $100 돌파"), (120, "CRITICAL", "유가 $120")],
        "change_pct": 5,
    },
    "BZ=F": {
        "name": "브렌트유",
        "absolute": [(100, "WARNING", "유가 $100 돌파"), (120, "CRITICAL", "유가 $120")],
        "change_pct": 5,
    },
    "GC=F": {
        "name": "금 선물",
        "absolute": [(3000, "WARNING", "금 $3,000 돌파")],
        "change_pct": 2,
    },
    "^TNX": {
        "name": "미국 10년물 금리",
        "absolute": [(5.0, "WARNING", "10년물 5% 돌파"), (5.5, "CRITICAL", "10년물 5.5%")],
        "change_bp": 10,
    },
    "^GSPC": {
        "name": "S&P 500",
        "absolute": [],
        "change_pct": 2,
    },
}

INDICATOR_THRESHOLDS_KR = {
    "KRW/USD": {
        "name": "원달러 환율",
        "absolute": [(1400, "WARNING", "원달러 1,400 돌파"), (1450, "CRITICAL", "원달러 1,450")],
        "change_pct": 1.5,
    },
    "KOSPI200N": {
        "name": "코스피200 야간선물",
        "absolute": [],
        "change_pct": 1.5,
    },
}

SENTIMENT_THRESHOLDS = {
    "cnn_fear_greed": {"low_warning": 20, "low_critical": 10, "high_warning": 80, "high_critical": 90},
    "crypto_fear_greed": {"low_warning": 15, "low_critical": 10, "high_warning": 85, "high_critical": 90},
}

# ─────────────────────────── LLM 설정 ───────────────────────────
GEMINI_MODEL = "gemini-2.5-flash"
LLM_TIMEOUT = 30
LLM_MAX_RETRIES = 3
LLM_DELAY_BETWEEN_CALLS = 4
LLM_BATCH_PAUSE = 10

# ─────────────────────────── 캐시 설정 ───────────────────────────
CACHE_TTL_HOURS = 24
TITLE_SIMILARITY_THRESHOLD = 0.7

# ─────────────────────────── 스코어링 ───────────────────────────
IMPACT_THRESHOLD = 5

# ─────────────────────────── 스케줄러 ───────────────────────────
SCHEDULE_CONFIG = {
    "pre_market":       {"hours": "6-8",    "minute": "*/5",  "sources": "all"},
    "market_hours":     {"hours": "9-15",   "minute": "*/5",  "sources": "all"},
    "after_market":     {"hours": "15-22",  "minute": "*/15", "sources": "all"},
    "overnight":        {"hours": "23,0-5", "minute": "0",    "sources": "global"},
    "indicator_monitor": {"minute": "*/10"},
    "night_futures":    {"hours": "18-23,0-5", "minute": "*/15"},
    "daily_report":     {"day_of_week": "mon-fri", "hour": "8,18", "minute": "0"},
    "batch_flush":      {"minute": "*/10"},
}
