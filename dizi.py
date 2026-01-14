import requests
import re
import sys
import time
from yabancidizibox_ext import extract_vidmody_link

def crawl_series(series_url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    base_url = "https://yabancidizibox.com"

    print(f"Dizi bilgileri alınıyor: {series_url}")
    
    try:
        response = requests.get(series_url, headers=headers)
        response.raise_for_status()
        html = response.text

        # Get Season links: href="/dizi/vikingler/sezon-1"
        # Example from user: <a href="/dizi/vikingler/sezon-1" ...>
        # We need to extract the path to avoid duplicates and ensure we have only seasons
        season_paths = re.findall(r'href=\"(/dizi/[^/]+/sezon-\d+)\"', html)
        season_paths = list(dict.fromkeys(season_paths)) # Remove duplicates

        if not season_paths:
            print("Hata: Sezon linkleri bulunamadı.")
            return

        print(f"{len(season_paths)} sezon bulundu.\n")

        for season_path in season_paths:
            season_url = f"{base_url}{season_path}"
            print(f"--- {season_path.split('/')[-1].capitalize()} İşleniyor ---")
            
            # Fetch Season Page
            s_response = requests.get(season_url, headers=headers)
            s_response.raise_for_status()
            s_html = s_response.text
            
            # Get Episode links: href="/dizi/vikingler/sezon-1/bolum-1"
            # Example: href="/dizi/vikingler/sezon-1/bolum-1"
            episode_paths = re.findall(r'href=\"(/dizi/[^/]+/sezon-\d+/bolum-\d+)\"', s_html)
            episode_paths = list(dict.fromkeys(episode_paths)) # Remove duplicates

            if not episode_paths:
                print("  Bulunan bölüm yok.")
                continue

            print(f"  {len(episode_paths)} bölüm bulundu.")

            for ep_path in episode_paths:
                ep_url = f"{base_url}{ep_path}"
                vidmody_link = extract_vidmody_link(ep_url)
                
                if vidmody_link:
                    # Clean up the display part s1/e01 etc from link if needed, 
                    # but extract_vidmody_link already does the heavy lifting
                    print(f"  {ep_path.split('/')[-1]}: {vidmody_link}")
                else:
                    print(f"  {ep_path.split('/')[-1]}: Hata (Link bulunamadı)")
                
                # Small delay to be polite
                time.sleep(0.2)
            print()

    except Exception as e:
        print(f"Bir hata oluştu: {e}")

if __name__ == "__main__":
    target = "https://yabancidizibox.com/dizi/vikingler"
    if len(sys.argv) > 1:
        target = sys.argv[1]
    
    crawl_series(target)
