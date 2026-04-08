"""뉴스 수집 모듈"""
from collectors.rss_collector import collect_rss
from collectors.html_collector import collect_html_fallback
from collectors.google_news import collect_google_news

__all__ = ["collect_rss", "collect_html_fallback", "collect_google_news"]
