import requests
import re
import sys
import json

def extract_vidmody_link(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        html = response.text

        # Extract IMDB ID (format: tt followed by numbers)
        # The site uses "imdb_id":"tt..." or just IDs in various locations
        imdb_match = re.search(r'\"imdb_id\"\s*:\s*\"(tt\d+)\"', html)
        if not imdb_match:
            # Try to find any ttID followed by its context
            imdb_match = re.search(r'(tt\d+)', html)
        
        if not imdb_match:
            print("Hata: IMDB ID bulunamadı.")
            return None

        imdb_id = imdb_match.group(1)

        # Detect if it's a TV series or a movie
        if "/dizi/" in url:
            # Extract Season and Episode from URL
            # Format: /sezon-(\d+)/bolum-(\d+)
            url_match = re.search(r'sezon-(\d+)/bolum-(\d+)', url)
            if not url_match:
                print("Hata: Sezon veya bölüm bilgisi URL'den okunamadı.")
                return None
            
            season = url_match.group(1)
            episode = url_match.group(2)

            # Construct Vidmody URL for series
            # Format: https://vidmody.com/vs/[IMDB]/s[S]/e[E]
            vidmody_url = f"https://vidmody.com/vs/{imdb_id}/s{int(season)}/e{int(episode):02d}"
        else:
            # Construct Vidmody URL for movies
            # Format: https://vidmody.com/vs/[IMDB]
            vidmody_url = f"https://vidmody.com/vs/{imdb_id}"
        
        return vidmody_url

    except Exception as e:
        print(f"Bir hata oluştu: {e}")
        return None

if __name__ == "__main__":
    target_url = "https://yabancidizibox.com/film/siccin-8"
    if len(sys.argv) > 1:
        target_url = sys.argv[1]
    
    print(f"Hedef URL: {target_url}")
    link = extract_vidmody_link(target_url)
    
    if link:
        print("\nBulunan Vidmody Linki:")
        print(link)
    else:
        print("\nLink oluşturulamadı.")
