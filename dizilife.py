import argparse
import base64
import hashlib
import logging
import os
import re
import sys
from typing import Iterable, Optional, Tuple, List, Set
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse

import requests
from bs4 import BeautifulSoup
from Crypto.Cipher import AES  # pip install pycryptodome

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:137.0) Gecko/20100101 Firefox/137.0",
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    }
)

IFRAME_HEADERS = {
    "Connection": "keep-alive",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "DNT": "1",
    "Sec-GPC": "1",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "cross-site",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

DEFAULT_BASE_URL = "https://dizi20.life"
DEFAULT_CATEGORIES = ("/diziler", "/filmler")


def _md5(data: bytes) -> bytes:
    return hashlib.md5(data).digest()


def _evp_bytes_to_key(passphrase: bytes, salt: bytes, key_len: int, iv_len: int) -> Tuple[bytes, bytes]:
    total = key_len + iv_len
    buf: List[bytes] = []
    prev = b""
    while sum(len(chunk) for chunk in buf) < total:
        prev = _md5(prev + passphrase + salt)
        buf.append(prev)
    derived = b"".join(buf)
    return derived[:key_len], derived[key_len:total]


def openssl_decrypt(base64_cipher: str, passphrase: str) -> Optional[str]:
    try:
        cipher_data = base64.b64decode(base64_cipher)
        if len(cipher_data) < 16 or cipher_data[:8] != b"Salted__":
            return None
        salt = cipher_data[8:16]
        enc = cipher_data[16:]
        key, iv = _evp_bytes_to_key(passphrase.encode(), salt, 32, 16)
        cipher = AES.new(key, AES.MODE_CBC, iv)
        plaintext = cipher.decrypt(enc)
        return plaintext.decode("utf-8")
    except Exception as err:
        logging.debug("Decrypt failed: %s", err)
        return None


def _first(patterns: Iterable[str], source: str) -> Optional[str]:
    for pat in patterns:
        match = re.search(pat, source, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _extract_stream_from_payload(payload: str) -> Optional[str]:
    src = _first([r'"source"\s*:\s*"([^"]+)"', r"[\"']source[\"']:\s*[\"']([^\"']+)[\"']"], payload)
    if src and src.startswith("http"):
        return src
    m3u8_match = re.search(r"(https://[^\s\"'<>]+\.m3u8[^\s\"'<>]*)", payload)
    if m3u8_match:
        return m3u8_match.group(1)
    if src and ".m3u8" in src:
        return src
    iframe_match = _first([r'src="(http[^"]+)"'], payload)
    if iframe_match and iframe_match.startswith("http"):
        return iframe_match
    return None


def _clean_playlist_url(url: str, token: Optional[str]) -> str:
    base = url.split("?token", 1)[0]
    if token:
        base = f"{base}{token}"
    return base.strip()


def _sanitize_title(title: Optional[str], season: Optional[str], episode: Optional[str]) -> Optional[str]:
    if not title:
        return None
    t = title.strip()
    # Genelde '|' sonrası site bilgisi gelir, onu at
    if '|' in t:
        t = t.split('|', 1)[0]
    # Ortak site/anahtar kelimeleri çıkar
    t = re.sub(r'\b(dizi\.life|dizilife|dizi life|izle|film izle|yabancı dizi izle)\b', '', t, flags=re.I)
    # Fazla açıklama yapan son parçaları kes (ör. " - yabancı ...")
    t = re.sub(r'\s*[-–—:|]\s*[^-–—:|]*$', '', t).strip()
    # Sezon/bölüm ifadelerini sil (tekrar ekleyeceğiz)
    t = re.sub(r'\b\d{1,2}\s*[.\-]?\s*sezon\b', '', t, flags=re.I)
    t = re.sub(r'\b\d{1,3}\s*[.\-]?\s*bölüm\b', '', t, flags=re.I)
    t = re.sub(r'\bİzle\b', '', t, flags=re.I)
    t = re.sub(r'\s{2,}', ' ', t).strip()
    # Küçük harfleri düzeltmek istenirse title() yeterli olacaktır
    return t.title() if t else None


def resolve_stream(page_url: str) -> Tuple[Optional[str], Optional[str]]:
    logging.debug("Resolving %s", page_url)
    main_resp = SESSION.get(page_url, timeout=15)
    main_resp.raise_for_status()
    soup = BeautifulSoup(main_resp.text, "html.parser")
    # Başlık (dizi ismi) çıkarımı: önce meta/og:title, sonra <title>, sonra h1 veya sınıf isimleri
    show_title = None
    og = soup.select_one("meta[property='og:title'], meta[name='og:title']")
    if og and og.get("content"):
        show_title = og["content"].strip()
    if not show_title and soup.title and soup.title.string:
        show_title = soup.title.string.strip()
    if not show_title:
        h = soup.select_one("h1, .title, .content-title, .film-title")
        if h:
            show_title = h.get_text(strip=True)

    # URL slug fallback (ör. /dizi/gassal/2-sezon-1-bolum/...)
    if not show_title:
        slug_match = re.search(r'/dizi/([^/]+)/', page_url, re.IGNORECASE)
        if slug_match:
            slug = slug_match.group(1)
            show_title = slug.replace('-', ' ').strip().title()

    iframe = soup.select_one("iframe#videoIframe, iframe[src*=player], iframe")
    if not iframe or not iframe.get("src"):
        logging.warning("Iframe not found for %s", page_url)
        return None, show_title

    iframe_url = iframe["src"]
    try:
        iframe_resp = SESSION.get(iframe_url, headers=IFRAME_HEADERS, timeout=15, allow_redirects=True)
        iframe_resp.raise_for_status()
        iframe_html = iframe_resp.text
    except requests.RequestException as exc:
        logging.warning("Iframe isteği başarısız (%s): %s", iframe_url, exc)
        # iframe alınamazsa bu sayfa için akış çözülemez; çağırana (load_sources) show title döner
        return None, show_title

    token = None
    token_match = re.search(r"'([^']*token[^']*)'", iframe_html, re.IGNORECASE)
    if token_match:
        token = token_match.group(1)
        logging.debug("Token: %s", token)

    decrypt_match = re.search(r'dct\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\)', iframe_html)
    if not decrypt_match:
        logging.warning("Cipher data missing in iframe for %s", page_url)
        return None, show_title

    cipher_text, passphrase = decrypt_match.groups()
    repl_match = re.search(r"\.replace\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)", iframe_html)
    replace_src, replace_dst = repl_match.groups() if repl_match else (None, None)

    decrypted = openssl_decrypt(cipher_text, passphrase)
    if not decrypted:
        logging.warning("Decryption failed for %s", page_url)
        return None, show_title

    if replace_src and replace_dst:
        decrypted = decrypted.replace(replace_src, replace_dst)

    stream_url = _extract_stream_from_payload(decrypted)
    if not stream_url and ".m3u8" in decrypted:
        stream_url = _first([r"(https://[^\s\"'<>]+\.m3u8[^\s\"'<>]*)"], decrypted)

    if not stream_url:
        logging.warning("Stream URL not detected for %s", page_url)
        return None, show_title

    cleaned = _clean_playlist_url(stream_url, token)
    final_url = cleaned if cleaned.startswith("http") else None

    # Sezon ve bölüm çıkarımı: önce URL'den, sonra sayfa içeriğinden
    season = None
    episode = None
    sepi_match = re.search(r'(\d+)-sezon-(\d+)-bolum', page_url, re.IGNORECASE)
    if sepi_match:
        season, episode = sepi_match.groups()
    else:
        # sayfa içeriğinde "1. Sezon" veya "2. Bölüm" gibi ifadeleri ara
        txt = soup.get_text(" ", strip=True)
        s_match = re.search(r'(\d{1,2})\s*[.\-]?\s*sezon', txt, re.IGNORECASE)
        e_match = re.search(r'(\d{1,3})\s*[.\-]?\s*bölüm', txt, re.IGNORECASE)
        if s_match:
            season = s_match.group(1)
        if e_match:
            episode = e_match.group(1)

    # Show title'ı site-eklerinden ve sezon/bölüm tekrarlarından temizle
    show_title = _sanitize_title(show_title, season, episode)

    # Gösterim başlığını birleştir
    display_title = show_title or None
    if display_title and (season or episode):
        parts = []
        if season:
            parts.append(f"{season}. Sezon")
        if episode:
            parts.append(f"{episode}. Bölüm")
        display_title = f"{display_title} - {' '.join(parts)}"
    # Eğer başlık hiç yoksa None döndürülür; çağıran load_sources default isim verebilir.
    return final_url, display_title


def build_playlist(entries: Iterable[Tuple[str, str, str, Optional[str]]]) -> str:
    lines = ["#EXTM3U"]
    for title, url, referrer, group in entries:
        # group-title ekle (varsa)
        if group:
            g = group.replace('"', '')  # tırnaklardan kurtul
            lines.append(f'#EXTINF:-1 group-title="{g}",{title}')
        else:
            lines.append(f"#EXTINF:-1,{title}")
        lines.append(f"#EXTVLCOPT:http-user-agent={SESSION.headers.get('User-Agent', '')}")
        lines.append(f"#EXTVLCOPT:http-referrer={referrer}")
        lines.append(url)
    return "\n".join(lines) + "\n"


def _is_show_page(url: str) -> bool:
	"""Basit kontrol: /dizi/ içeriyorsa ve doğrudan bölüm işaretleri yoksa show ana sayfası say."""
	if "/dizi/" not in url:
		return False
	# Eğer URL zaten sezon/bölüm veya bölüm ID'si içeriyorsa show sayfası değil
	if re.search(r'(\d+)-sezon-(\d+)-bolum', url, re.IGNORECASE):
		return False
	if re.search(r'/bolum/|/sezon[-/]\d+|/\d{4,}$', url, re.IGNORECASE):
		return False
	return True


def _is_listing_page(url: str, soup: Optional[BeautifulSoup] = None) -> bool:
    """Listing sayfası mı? (/diziler, /filmler veya içerik kartı çoksa True)."""
    if "/diziler" in url or "/filmler" in url:
        return True
    if soup is None:
        try:
            soup = _get_soup(url)
        except Exception:
            return False
    # Eğer sayfada çok sayıda içerik kartı varsa listing sayfası kabul et
    cards = soup.select("div.content-card, a.content-card, .content-card")
    return len(cards) >= 5


def _collect_shows_from_listing(listing_url: str) -> List[Tuple[str, Optional[str]]]:
    """Tek bir listing sayfasından tüm show (detay) sayfalarını toplar ve span.credit-value bilgisini alır."""
    shows: List[Tuple[str, Optional[str]]] = []
    seen: Set[str] = set()
    next_page = listing_url
    max_pages = 50
    pages_tried = 0
    while next_page and next_page not in seen:
        pages_tried += 1
        if pages_tried > max_pages:
            logging.warning("Maksimum sayfa sayısına ulaşıldı, durduruluyor: %s", listing_url)
            break
        seen.add(next_page)
        logging.debug("Listing sayfası taranıyor: %s", next_page)
        try:
            soup = _get_soup(next_page)
        except requests.RequestException as exc:
            logging.warning("Listing sayfası atlandı (%s): %s", next_page, exc)
            break
        cards = soup.select("div.content-card, a.content-card")
        if not cards:
            cards = soup.select("[data-url], .content-card a[href]")
        for card in cards:
            candidate = card if card.name == "a" else card.select_one("a[href]") or card
            target = candidate.get("data-url") or candidate.get("href")
            if not target:
                continue
            abs_url = urljoin(listing_url, target).rstrip("/")
            if abs_url in seen:
                continue
            # group bilgisi card içinde bulunabilir
            group = None
            # card genellikle bir element; arayalım
            try:
                credit = card.select_one("span.credit-value")
                if credit:
                    group_text = credit.get_text(strip=True)
                    if group_text:
                        group = group_text
            except Exception:
                group = None
            seen.add(abs_url)
            shows.append((abs_url, group))
        # next page
        next_href = None
        for selector in ("a[rel=next]", ".pagination a.next", ".pagination .next a"):
            candidate = soup.select_one(selector)
            if candidate and candidate.get("href"):
                next_href = candidate["href"]
                break
        if not next_href:
            for candidate in soup.select(".pagination a"):
                if candidate.get("href") and candidate.get_text(strip=True).lower() in {"sonraki", "next"}:
                    next_href = candidate["href"]
                    break
        if next_href:
            next_page = urljoin(listing_url, next_href)
        else:
            # fallback: next link yoksa URL'deki page parametresini artırmayı dene
            try:
                parsed = urlparse(next_page)
                qs = parse_qs(parsed.query)
                current_page = int(qs.get("page", ["1"])[0]) if qs.get("page") else 1
                next_page_num = current_page + 1
                qs["page"] = [str(next_page_num)]
                new_query = urlencode({k: v[0] for k, v in qs.items()})
                candidate_parts = (parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment)
                candidate_url = urlunparse(candidate_parts)
                if candidate_url in seen:
                    next_page = None
                else:
                    logging.debug("Next href bulunamadı, fallback ile sayfa arttırılıyor: %s", candidate_url)
                    next_page = candidate_url
            except Exception:
                next_page = None
    logging.info("Listingten %d dizi sayfası bulundu.", len(shows))
    return list(dict.fromkeys(shows))


def load_sources(urls: Iterable[str]) -> List[Tuple[str, str, str, Optional[str]]]:
    resolved: List[Tuple[str, str, str, Optional[str]]] = []
    # Eğer tek bir URL verildi ve bu bir listing ise önce tüm dizilere genişlet
    expanded_urls: List[Tuple[str, Optional[str]]] = []
    for u in urls:
        try:
            if _is_listing_page(u):
                logging.info("Listing URL tespit edildi, diziler toplanıyor: %s", u)
                expanded = _collect_shows_from_listing(u)
                if expanded:
                    expanded_urls.extend(expanded)
                    continue
        except Exception:
            pass
        expanded_urls.append((u, None))

    for idx, (url, group) in enumerate(expanded_urls, start=1):
        title_fallback = f"DiziLife #{idx}"
        stream, title = resolve_stream(url)
        if stream:
            use_title = title or title_fallback
            logging.info("Resolved %s -> %s", use_title, stream)
            resolved.append((use_title, stream, url, group))
            continue

        # Eğer akış bulunamadıysa ve URL bir show ana sayfasına benziyorsa,
        # o gösterinin tüm bölümlerini topla ve her bir bölüm için çözmeye çalış.
        if _is_show_page(url):
            logging.info("Show ana sayfası tespit edildi, bölümler toplanıyor: %s", url)
            episode_urls = _collect_episode_urls(url)
            if not episode_urls:
                logging.error("Show için bölüm bulunamadı: %s", url)
                continue
            for ep_idx, ep_url in enumerate(episode_urls, start=1):
                ep_stream, ep_title = resolve_stream(ep_url)
                if ep_stream:
                    use_title = ep_title or f"{title_fallback} - Bölüm {ep_idx}"
                    logging.info("Resolved %s -> %s", use_title, ep_stream)
                    resolved.append((use_title, ep_stream, ep_url, group))
                else:
                    logging.warning("Bölüm atlandı (akış bulunamadı): %s", ep_url)
            continue

        logging.error("Skipping %s, stream not found.", url)
    return resolved


def _get_soup(url: str) -> BeautifulSoup:
    resp = SESSION.get(url, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def _ensure_leading_slash(path: str) -> str:
    return path if path.startswith("/") else f"/{path}"


def _collect_listing_urls(base_url: str, category_paths: Iterable[str]) -> List[str]:
    show_urls: List[str] = []
    seen: Set[str] = set()
    for raw_path in category_paths:
        path = _ensure_leading_slash(raw_path.strip())
        next_page = urljoin(base_url, path)
        visited_pages: Set[str] = set()
        while next_page and next_page not in visited_pages:
            visited_pages.add(next_page)
            logging.debug("Kategori taranıyor: %s", next_page)
            try:
                soup = _get_soup(next_page)
            except requests.RequestException as exc:
                logging.warning("Kategori sayfası atlandı (%s): %s", next_page, exc)
                break
            cards = soup.select("div.content-card, a.content-card")
            if not cards:
                cards = soup.select("[data-url], .content-card a[href]")
            new_count = 0
            for card in cards:
                candidate = card if card.name == "a" else card.select_one("a[href]") or card
                target = candidate.get("data-url") or candidate.get("href")
                if not target:
                    continue
                abs_url = urljoin(base_url, target).rstrip("/")
                if abs_url in seen:
                    continue
                seen.add(abs_url)
                show_urls.append(abs_url)
                new_count += 1
            if new_count == 0:
                break
            next_href = None
            for selector in ("a[rel=next]", ".pagination a.next", ".pagination .next a"):
                candidate = soup.select_one(selector)
                if candidate and candidate.get("href"):
                    next_href = candidate["href"]
                    break
            if not next_href:
                for candidate in soup.select(".pagination a"):
                    if candidate.get("href") and candidate.get_text(strip=True).lower() in {"sonraki", "next"}:
                        next_href = candidate["href"]
                        break
            if next_href:
                candidate_url = urljoin(base_url, next_href)
                next_page = candidate_url if candidate_url not in visited_pages else None
            else:
                break
    logging.info("Toplam %d içerik sayfası bulundu.", len(show_urls))
    return show_urls


def _collect_episode_urls(show_url: str) -> List[str]:
    try:
        soup = _get_soup(show_url)
    except requests.RequestException as exc:
        logging.warning("Detay sayfası atlandı (%s): %s", show_url, exc)
        return []
    episodes: List[str] = []
    seen = set()
    cards = soup.select("div.episode-card")
    if cards:
        for card in cards:
            episode_id = card.get("data-episode-id")
            season = card.get("data-season-number")
            episode = card.get("data-episode-number")
            if not all([episode_id, season, episode]):
                continue
            episode_url = f"{show_url.rstrip('/')}/{season}-sezon-{episode}-bolum/{episode_id}"
            if episode_url in seen:
                continue
            seen.add(episode_url)
            episodes.append(episode_url)
        return episodes

    # Eğer episode-card yoksa: sayfadaki tüm <a href> linklerinden bölüm/siyon linklerini seç
    anchors = soup.select("a[href]")
    candidates: List[str] = []
    for a in anchors:
        href = a.get("href")
        if not href:
            continue
        abs_url = urljoin(show_url, href).rstrip("/")
        if abs_url in seen:
            continue
        # Bölüm/season içeren URL desenleri
        if re.search(r'(\d+)-sezon-(\d+)-bolum', abs_url, re.IGNORECASE) \
           or re.search(r'/bolum/', abs_url, re.IGNORECASE) \
           or re.search(r'/sezon[-/]\d+', abs_url, re.IGNORECASE):
            seen.add(abs_url)
            candidates.append(abs_url)

    # Ek konteyner seçicilerde de arama yap
    if not candidates:
        for selector in (".episodes a[href]", ".episode-list a[href]", ".episodes-list a[href]", ".season a[href]"):
            for a in soup.select(selector):
                href = a.get("href")
                if not href:
                    continue
                abs_url = urljoin(show_url, href).rstrip("/")
                if abs_url in seen:
                    continue
                seen.add(abs_url)
                candidates.append(abs_url)

    # Deduplicate ve sezon/bölüm numarasına göre sıralama
    def _ep_key(u: str):
        m = re.search(r'(\d+)-sezon-(\d+)-bolum', u, re.IGNORECASE)
        if m:
            return (int(m.group(1)), int(m.group(2)))
        # alternatif desenler
        m2 = re.search(r'/sezon[-/](\d+).*?bolum[-/](\d+)', u, re.IGNORECASE)
        if m2:
            return (int(m2.group(1)), int(m2.group(2)))
        nums = re.findall(r'(\d+)', u)
        if len(nums) >= 2:
            return (int(nums[-2]), int(nums[-1]))
        if nums:
            return (0, int(nums[-1]))
        return (9999, 0)

    unique_candidates = []
    seen2 = set()
    for c in candidates:
        if c in seen2:
            continue
        seen2.add(c)
        unique_candidates.append(c)

    if unique_candidates:
        unique_candidates.sort(key=_ep_key)
        return unique_candidates

    # Hiç bölüm bulunmadıysa, gösterim sayfasını tek bölüm olarak döndür
    return [show_url]


def collect_all_episode_urls(base_url: str, category_paths: Iterable[str]) -> List[str]:
    all_urls: List[str] = []
    seen = set()
    for show_url in _collect_listing_urls(base_url, category_paths):
        for episode_url in _collect_episode_urls(show_url):
            if episode_url in seen:
                continue
            seen.add(episode_url)
            all_urls.append(episode_url)
    logging.info("Toplam %d oynatma bağlantısı derlendi.", len(all_urls))
    return all_urls


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DiziLife M3U oluşturucu")
    parser.add_argument("urls", nargs="*", help="DiziLife içerik/ bölüm URL’leri")
    parser.add_argument("-f", "--file", help="URL listesi içeren dosya")
    parser.add_argument("-o", "--output", default="playlist.m3u", help="Çıkış dosyası")
    parser.add_argument("-v", "--verbose", action="store_true", help="Ayrıntılı log")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Kaynak site ana adresi")
    parser.add_argument(
        "--categories",
        nargs="+",
        default=list(DEFAULT_CATEGORIES),
        help="Taranacak kategori yolları (varsayılan: /diziler /filmler)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s - %(message)s",
    )

    urls: List[str] = list(args.urls)
    if args.file:
        if not os.path.exists(args.file):
            logging.error("Dosya bulunamadı: %s", args.file)
            return 1
        with open(args.file, "r", encoding="utf-8") as handle:
            urls.extend(line.strip() for line in handle if line.strip())
    if not urls and not sys.stdin.closed:
        stdin_data = [line.strip() for line in sys.stdin if line.strip()]
        urls.extend(stdin_data)
    if not urls:
        logging.info("Manuel URL sağlanmadı, kategoriler otomatik taranıyor.")
        urls.extend(collect_all_episode_urls(args.base_url, args.categories))
    urls = list(dict.fromkeys(urls))
    if not urls:
        logging.error("Hiçbir URL bulunamadı. Kategori listesi veya bağlantılar boş.")
        return 1

    playlist_entries = load_sources(urls)
    if not playlist_entries:
        logging.error("Hiçbir akış çözülemedi.")
        return 1

    playlist_text = build_playlist(playlist_entries)
    with open(args.output, "w", encoding="utf-8") as out_file:
        out_file.write(playlist_text)
    logging.info("Playlist yazıldı: %s", args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
