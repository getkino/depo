
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cizgivedizi_merged_all.py
-------------------------
- ÇizgiVeDizi scraper mantığı (cizgivedizi_scraper) + toplu indirme (dump_all) tek dosyada birleşik.
- Tüm dizileri çeker, klasör içinde her dizi için ayrı JSON ve ayrıca ALL toplu JSON üretir.

Kullanım örnekleri:
    # Varsayılan çıktı: ./output
    python cizgivedizi_merged_all.py dump-all

    # Özel klasöre yaz, eşzamanlı iş parçacığı sayısını 4 yap
    python cizgivedizi_merged_all.py dump-all --out-dir C:/temp/cizgi --workers 4

    # İframe çözmeden sadece bölümleri yaz (daha hızlı)
    python cizgivedizi_merged_all.py dump-all --no-iframe

Notlar:
- Siteye aşırı yüklenmemek için varsayılan eşzamanlılık sınırlıdır.
- Çıktılar UTF-8 olarak yazılır.
"""

from __future__ import annotations

import os
import re
import json
import time
import argparse
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup

# =======================
#  Scraper (inline)
# =======================

BASE_URL = "https://cizgivedizi.com"
POSTER_PREPEND = "https://res.cloudinary.com/abhisheksaha/image/fetch/f_auto/"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": BASE_URL + "/",
    "Connection": "close",
}

@dataclass
class Series:
    slug: str
    title: str
    url: str
    poster: Optional[str] = None
    poster_cdn: Optional[str] = None
    plot: Optional[str] = None
    tags: Optional[str] = None

@dataclass
class Episode:
    title: str
    url: str
    season: Optional[int] = None
    episode: Optional[int] = None

@dataclass
class EpisodeLinks:
    url: str
    iframe_src: Optional[str] = None
    host: Optional[str] = None

def _make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(DEFAULT_HEADERS)
    return s

def _fix_url(u: str) -> str:
    return urljoin(BASE_URL + "/", u)

def _poster_cdn_url(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    absolute = _fix_url(raw)
    return POSTER_PREPEND + absolute

def _smart_split_kv(line: str):
    s = line.strip().lstrip("\ufeff")
    if not s or s.startswith("#") or s.startswith("//"):
        return None
    if s.startswith("|"):
        s = s[1:]
        if "=" in s:
            k, v = s.split("=", 1)
            return k.strip(), v.strip()
    if "=" in s:
        k, v = s.split("=", 1)
        return k.strip(), v.strip()
    for sep in (":", "\t", "|"):
        if sep in s:
            k, v = s.split(sep, 1)
            k = k.lstrip("|").strip()
            return k, v.strip()
    parts = s.split()
    if len(parts) >= 2:
        return parts[0].lstrip("|"), " ".join(parts[1:]).strip()
    return None

def get_text_map(path: str, session: Optional[requests.Session] = None) -> Dict[str, str]:
    sess = session or _make_session()
    url = _fix_url(path)
    r = sess.get(url, timeout=20)
    r.encoding = "utf-8"
    r.raise_for_status()
    text = r.text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln for ln in text.split("\n") if ln.strip()]
    pairs = []
    for ln in lines:
        kv = _smart_split_kv(ln)
        if kv and kv[0] != "":
            pairs.append(kv)
    return dict(pairs)

def list_series(session: Optional[requests.Session] = None) -> List[Series]:
    sess = session or _make_session()
    isim = get_text_map("/dizi/isim.txt", sess)

    poster = {}
    plot = {}

    for candidate in ("/dizi/poster.txt", "/dizi/ozet.txt"):
        try:
            m = get_text_map(candidate, sess)
            if "poster" in candidate:
                poster = m
            else:
                plot = m
        except Exception:
            pass

    tags = {}
    for candidate in ("/dizi/etiket.txt", "/etiket.txt"):
        try:
            m = get_text_map(candidate, sess)
            if m:
                tags = m
                break
        except Exception:
            continue

    out: List[Series] = []
    for slug, title in isim.items():
        url = f"{BASE_URL}/dizi/{slug}/"
        raw_poster = poster.get(slug)
        out.append(
            Series(
                slug=slug,
                title=title,
                url=url,
                poster=raw_poster,
                poster_cdn=_poster_cdn_url(raw_poster) if raw_poster else None,
                plot=plot.get(slug),
                tags=tags.get(slug),
            )
        )
    return out

def get_episodes(slug: str, session: Optional[requests.Session] = None) -> List[Episode]:
    sess = session or _make_session()
    url = f"{BASE_URL}/dizi/{slug}/"
    r = sess.get(url, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    episodes: List[Episode] = []
    for a in soup.select("a.bolum"):
        href = a.get("href") or ""
        abs_url = _fix_url(href)

        title_el = a.select_one(".card-title")
        title_txt = title_el.get_text(strip=True) if title_el else ""
        if ")" in title_txt:
            title_clean = title_txt.split(")", 1)[-1].strip() or title_txt
        else:
            title_clean = title_txt

        season = None
        season_raw = a.get("data-sezon")
        if season_raw:
            try:
                season = int(season_raw)
            except Exception:
                season = None

        ep_num = None
        last_seg = urlparse(abs_url).path.rstrip("/").split("/")[-1]
        m = re.search(r"(\d+)", last_seg)
        if m:
            try:
                ep_num = int(m.group(1))
            except Exception:
                ep_num = None

        episodes.append(Episode(title=title_clean or last_seg, url=abs_url, season=season, episode=ep_num))

    return episodes

def get_episode_links(episode_url: str, session: Optional[requests.Session] = None) -> EpisodeLinks:
    sess = session or _make_session()
    url = _fix_url(episode_url)
    r = sess.get(url, timeout=25)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    iframe = soup.select_one("iframe")
    src = None
    host = None
    if iframe:
        src = iframe.get("src")
        if src:
            src = _fix_url(src)
            try:
                host = urlparse(src).netloc
            except Exception:
                host = None

    return EpisodeLinks(url=url, iframe_src=src, host=host)

# =======================
#  Bulk dumper
# =======================

def sanitize_filename(name: str) -> str:
    return re.sub(r'[^A-Za-z0-9._-]+', '_', name, flags=re.UNICODE)

def dump_series(slug: str, sess: requests.Session, include_iframe: bool = True) -> dict:
    """Tek bir dizi için meta + bölüm + (opsiyonel) iframe linkleri döndürür."""
    # meta
    all_meta = {s.slug: s for s in list_series(sess)}
    meta = all_meta.get(slug) or Series(slug=slug, title=slug, url=f"{BASE_URL}/dizi/{slug}/")

    # bölümler
    episodes = get_episodes(slug, sess)
    result_eps = []
    for e in episodes:
        ep_dict = {"title": e.title, "url": e.url, "season": e.season, "episode": e.episode}
        if include_iframe:
            try:
                links = get_episode_links(e.url, sess)
                ep_dict.update({"iframe_src": links.iframe_src, "host": links.host})
            except Exception:
                ep_dict.update({"iframe_src": None, "host": None})
        result_eps.append(ep_dict)

    return {
        "slug": meta.slug,
        "title": meta.title,
        "url": meta.url,
        "poster": meta.poster,
        "poster_cdn": meta.poster_cdn,
        "plot": meta.plot,
        "tags": meta.tags,
        "episodes": result_eps,
    }

def cmd_dump_all(args):
    out_dir = args.out_dir
    os.makedirs(out_dir, exist_ok=True)
    per_dir = os.path.join(out_dir, "series")
    os.makedirs(per_dir, exist_ok=True)

    sess = _make_session()
    all_series = list_series(sess)
    slugs = [s.slug for s in all_series]

    print(f"[i] Toplam dizi: {len(slugs)}")
    workers = max(1, int(args.workers))
    include_iframe = not args.no_iframe

    all_results = []

    def _worker(slug):
        try:
            data = dump_series(slug, sess, include_iframe=include_iframe)
            # per-series file
            fname = sanitize_filename(slug) + ".json"
            fpath = os.path.join(per_dir, fname)
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return data, slug, None
        except Exception as e:
            return None, slug, str(e)

    if workers == 1:
        for slug in slugs:
            data, s, err = _worker(slug)
            if err:
                print(f"[!] {s} hata: {err}")
            elif data:
                all_results.append(data)
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(_worker, slug): slug for slug in slugs}
            for fut in as_completed(futs):
                data, s, err = fut.result()
                if err:
                    print(f"[!] {s} hata: {err}")
                elif data:
                    all_results.append(data)

    # aggregated all.json
    all_path = os.path.join(out_dir, "all.json")
    with open(all_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    print(f"[+] Bitti. Per-dizi JSON klasörü: {per_dir}")
    print(f"[+] Toplu JSON: {all_path}")

def main():
    p = argparse.ArgumentParser(description="ÇizgiVeDizi - Tüm diziler için toplu JSON çıkarıcı (tek dosya)")
    sub = p.add_subparsers()

    p_dump = sub.add_parser("dump-all", help="Tüm dizileri çek, per-dizi JSON + all.json yaz")
    p_dump.add_argument("--out-dir", default="output", help="Çıktı klasörü (varsayılan: ./output)")
    p_dump.add_argument("--workers", default="3", help="Eşzamanlı iş parçacığı sayısı (varsayılan: 3)")
    p_dump.add_argument("--no-iframe", action="store_true", help="İframe çözümünü kapat (daha hızlı)")
    p_dump.set_defaults(func=cmd_dump_all)

    args = p.parse_args()
    if not hasattr(args, "func"):
        p.print_help()
        return
    args.func(args)

if __name__ == "__main__":
    main()
