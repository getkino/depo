import requests
from bs4 import BeautifulSoup
import re
import base64
from urllib.parse import urljoin, quote

BASE_URL = "https://hdfilmsite.com/"
PROXY = "https://2.nejyoner19.workers.dev/?url="  # Proxy prefix

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

m3u_content = ["#EXTM3U"]

def page_url(page: int) -> str:
    if page <= 1:
        return BASE_URL
    return urljoin(BASE_URL, f"yeni-filmler/{page}")

def fetch(url: str) -> BeautifulSoup | None:
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, 'html.parser')
    except requests.exceptions.RequestException as e:
        print(f"İstek hatası ({url}): {e}")
        return None

def absolutize(url: str) -> str:
    if not url:
        return ""
    url = url.strip()
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return urljoin(BASE_URL, url)
    if url.startswith(("http://", "https://")):
        return url
    return urljoin(BASE_URL, url)

def extract_poster_url(soup: BeautifulSoup) -> str:
    # 1) <img itemprop="image">
    img = soup.find("img", attrs={"itemprop": "image"})
    if img:
        for attr in ("src", "data-src", "data-lazy-src"):
            if img.has_attr(attr) and img[attr]:
                return absolutize(img[attr])
    # 2) <meta property="og:image">
    meta = soup.find("meta", attrs={"property": "og:image"})
    if meta and meta.get("content"):
        return absolutize(meta["content"])
    return ""

total_added = 0

for page in range(1, 101):  # 1..5
    list_url = page_url(page)
    print(f"\n=== Sayfa {page}: {list_url} ===")

    soup = fetch(list_url)
    if not soup:
        continue

    lists_div = soup.find('div', class_='lists')
    if not lists_div:
        print("class='lists' bulunamadı, sayfa atlanıyor.")
        continue

    movie_boxes = lists_div.find_all('div', class_='movie_box')
    if not movie_boxes:
        print("Film kutusu bulunamadı.")
        continue

    for movie_box in movie_boxes:
        image_link = movie_box.find('a', class_='image')
        if not image_link or 'href' not in image_link.attrs:
            continue

        movie_url = urljoin(BASE_URL, image_link['href'])
        movie_soup = fetch(movie_url)
        if not movie_soup:
            continue

        # Başlık
        title_tag = movie_soup.find('h1') or movie_soup.find('title')
        movie_title = title_tag.text.strip() if title_tag else movie_url.rstrip('/').split('/')[-1].replace('-', ' ').title()

        # Tür
        genre = "Bilinmiyor"
        genre_block = movie_soup.find('b', string="Film Türü")
        if genre_block:
            span_tag = genre_block.find_next('span')
            if span_tag and span_tag.find('a'):
                genre = span_tag.find('a').get_text(strip=True)

        # Poster
        poster_url = extract_poster_url(movie_soup)

        # ilkpartkod -> iframe src
        scripts = movie_soup.find_all('script')
        iframe_url = None
        for script in scripts:
            if script.string and "var ilkpartkod" in script.string:
                match = re.search(r"var\s+ilkpartkod\s*=\s*'([^']+)';", script.string)
                if match:
                    try:
                        decoded_string = base64.b64decode(match.group(1)).decode('utf-8', errors='ignore')
                        iframe_match = re.search(r'src="([^"]+)"', decoded_string)
                        if iframe_match:
                            iframe_url = iframe_match.group(1)
                    except Exception:
                        pass
                break

        if not iframe_url:
            continue

        # iframe sayfasından var id
        iframe_soup = fetch(iframe_url)
        if not iframe_soup:
            continue

        video_id = None
        for script in iframe_soup.find_all('script'):
            if script.string and "var id =" in script.string:
                id_match = re.search(r"var\s+id\s*=\s*'([^']+)';", script.string)
                if id_match:
                    video_id = id_match.group(1)
                    break

        if not video_id:
            continue

        # Asıl URL + proxy
        real_url = f"https://vidmody.com/vs/{video_id}"
        # URL'i query parametre olarak eklerken güvenli olsun diye encode edelim:
        new_url = PROXY + quote(real_url, safe=":/?&=%")

        # M3U'ya ekle (tvg-id=video_id, tvg-name ve tvg-logo dahil)
        if poster_url:
            m3u_content.append(
                f'#EXTINF:-1 tvg-id="{video_id}" tvg-name="{movie_title}" tvg-logo="{poster_url}" group-title="{genre}",{movie_title}'
            )
        else:
            m3u_content.append(
                f'#EXTINF:-1 tvg-id="{video_id}" tvg-name="{movie_title}" group-title="{genre}",{movie_title}'
            )
        m3u_content.append(new_url)

        # Terminal çıktısı: URL yerine film adı
        print(f"✓ Eklendi: {movie_title}")
        total_added += 1

print(f"\nToplam eklenen film: {total_added}")

# M3U dosyası kaydet
with open("movies.m3u", "w", encoding="utf-8") as f:
    f.write("\n".join(m3u_content))
print("\nM3U dosyası oluşturuldu: movies.m3u")
