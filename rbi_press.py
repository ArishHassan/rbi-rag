from html.parser import HTMLParser
from typing import Dict, List, Optional
from urllib.parse import urljoin

import requests


RBI_PRESS_RELEASE_URL = "https://rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx"


class RBIPressReleaseParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.current_date: Optional[str] = None
        self.releases: List[Dict[str, str]] = []
        self._in_tr = False
        self._in_header_cell = False
        self._active_anchor: Optional[Dict[str, str]] = None
        self._row: Dict[str, str] = {}
        self._header_text: List[str] = []
        self._last_pdf = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        tag = tag.lower()

        if tag == "tr":
            self._in_tr = True
            self._row = {}
            self._header_text = []
            self._last_pdf = False
            return

        if not self._in_tr:
            return

        if tag == "td" and "tableheader" in attrs_dict.get("class", ""):
            self._in_header_cell = True
            return

        if tag == "a":
            href = attrs_dict.get("href", "")
            self._active_anchor = {"href": href, "text": ""}
            if href.lower().endswith(".pdf"):
                self._last_pdf = True
                self._row["pdf_url"] = href
            return

        if tag == "img" and self._active_anchor is not None:
            alt = attrs_dict.get("alt", "")
            if alt.startswith("PDF - ") and not self._row.get("title"):
                self._row["title"] = alt.replace("PDF - ", "", 1).strip()

    def handle_data(self, data):
        if not self._in_tr:
            return

        if self._in_header_cell:
            self._header_text.append(data)
        elif self._active_anchor is not None:
            self._active_anchor["text"] += data
        elif self._last_pdf:
            size = " ".join(data.split())
            if size:
                self._row["size"] = size

    def handle_endtag(self, tag):
        tag = tag.lower()

        if tag == "a" and self._active_anchor is not None:
            href = self._active_anchor["href"]
            text = " ".join(self._active_anchor["text"].split())

            if "BS_PressReleaseDisplay.aspx?prid=" in href and text:
                self._row["title"] = text
                self._row["detail_url"] = urljoin(RBI_PRESS_RELEASE_URL, href)
                self._row["id"] = href.rsplit("prid=", 1)[-1]
            elif href.lower().endswith(".pdf"):
                self._row["pdf_url"] = urljoin(RBI_PRESS_RELEASE_URL, href)

            self._active_anchor = None
            return

        if tag == "td" and self._in_header_cell:
            self._in_header_cell = False
            return

        if tag == "tr" and self._in_tr:
            if self._header_text:
                date = " ".join("".join(self._header_text).split())
                if date:
                    self.current_date = date
            elif self._row.get("title") and self._row.get("pdf_url"):
                self._row["published_date"] = self.current_date or ""
                self._row["source_name"] = self._source_name(self._row)
                self.releases.append(self._row.copy())

            self._in_tr = False
            self._in_header_cell = False
            self._active_anchor = None
            self._last_pdf = False

    @staticmethod
    def _source_name(row: Dict[str, str]) -> str:
        release_id = row.get("id")
        title = row.get("title", "RBI Press Release")
        if release_id:
            return f"{title} [RBI PR {release_id}]"
        return title


def fetch_latest_press_releases(search: str = "", limit: int = 50) -> List[Dict[str, str]]:
    response = requests.get(
        RBI_PRESS_RELEASE_URL,
        timeout=20,
        headers={"User-Agent": "Mozilla/5.0 RBI-RAG/1.0"},
    )
    response.raise_for_status()

    parser = RBIPressReleaseParser()
    parser.feed(response.text)

    releases = parser.releases
    if search:
        needle = search.lower()
        releases = [
            item for item in releases
            if needle in item.get("title", "").lower()
            or needle in item.get("published_date", "").lower()
        ]

    return releases[:limit]
