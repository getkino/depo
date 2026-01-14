import requests
import re
import time
import sys
from yabancidizibox_ext import extract_vidmody_link

def crawl_series_episodes(series_url, headers, base_url):
    """Crawl all seasons and episodes for a given series URL."""
    print(f"\n  >> Dizi taranıyor: {series_url}")
    try:
        response = requests.get(series_url, headers=headers)
        response.raise_for_status()
        html = response.text

        # Extract Season links
        season_paths = re.findall(r'href=\"(/dizi/[^/]+/sezon-\d+)\"', html)
        season_paths = list(dict.fromkeys(season_paths))

        if not season_paths:
            print("  !! Sezon bulunamadı.")
            return

        for season_path in season_paths:
            season_url = f"{base_url}{season_path}"
            print(f"    -- {season_path.split('/')[-1].capitalize()} --")
            
            s_response = requests.get(season_url, headers=headers)
            s_response.raise_for_status()
            s_html = s_response.text
            
            # Extract Episode links
            episode_paths = re.findall(r'href=\"(/dizi/[^/]+/sezon-\d+/bolum-\d+)\"', s_html)
            episode_paths = list(dict.fromkeys(episode_paths))

            for ep_path in episode_paths:
                ep_url = f"{base_url}{ep_path}"
                vidmody_link = extract_vidmody_link(ep_url)
                
                if vidmody_link:
                    print(f"      {ep_path.split('/')[-1]}: {vidmody_link}")
                else:
                    print(f"      {ep_path.split('/')[-1]}: Hata")
                
                time.sleep(0.1)
    except Exception as e:
        print(f"  !! Dizi hatası: {e}")

def discover_and_crawl_series(max_pages=1):
    api_base_url = "https://yabancidizibox.com/api/discover?contentType=series&limit=24"
    base_url = "https://yabancidizibox.com"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Referer': 'https://yabancidizibox.com/kesfet',
    }

    print(f"Dizi Keşfet sayfasından taranıyor (Maksimum {max_pages} sayfa)...")

    for page in range(1, max_pages + 1):
        api_url = f"{api_base_url}&page={page}"
        print(f"\n=== Keşfet Sayfası {page} ===")
        
        try:
            response = requests.get(api_url, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            series_list = data.get('movies', []) # API uses 'movies' key even for series
            
            if not series_list:
                print("Dizi bulunamadı.")
                break

            for series in series_list:
                title = series.get('title', series.get('name', 'Bilinmeyen Dizi'))
                slug = series.get('slug')
                
                if not slug:
                    continue
                    
                series_url = f"{base_url}/dizi/{slug}"
                print(f"\n[*] İşleniyor: {title}")
                
                crawl_series_episodes(series_url, headers, base_url)
                
                # Delay between series
                time.sleep(0.5)

            if page >= data.get('totalPages', max_pages):
                break

        except Exception as e:
            print(f"Keşfet hatası (Sayfa {page}): {e}")
            break

if __name__ == "__main__":
    # Test için 1 sayfa yeterli, çok fazla link çıkacaktır
    discover_and_crawl_series(max_pages=1)
