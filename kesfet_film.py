import requests
import re
import json
import time

# Import the extraction logic from the other file
from yabancidizibox_ext import extract_vidmody_link

def crawl_discover_movies(max_pages=3):
    base_api_url = "https://yabancidizibox.com/api/discover?contentType=movie&limit=20"
    base_url = "https://yabancidizibox.com"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Referer': 'https://yabancidizibox.com/kesfet',
    }

    total_extracted = 0
    
    for page in range(1, max_pages + 1):
        api_url = f"{base_api_url}&page={page}"
        print(f"\n--- Sayfa {page} getiriliyor ---\n")
        
        try:
            response = requests.get(api_url, headers=headers)
            response.raise_for_status()
            
            try:
                data = response.json()
            except Exception:
                print(f"Hata: Sayfa {page} JSON formatında değil.")
                break

            movies = data.get('movies', [])
            
            if not movies:
                print(f"Sayfa {page} boş veya film bulunamadı.")
                break

            print(f"{len(movies)} film bulundu. Linkler çıkartılıyor...")
            
            for movie in movies:
                title = movie.get('title', movie.get('name', 'Bilinmeyen Film'))
                slug = movie.get('slug')
                
                if not slug:
                    continue
                    
                movie_url = f"{base_url}/film/{slug}"
                print(f"[{total_extracted + 1}] İşleniyor: {title}")
                
                vidmody_link = extract_vidmody_link(movie_url)
                
                if vidmody_link:
                    print(f"  -> Vidmody: {vidmody_link}")
                    total_extracted += 1
                else:
                    print(f"  -> Hata: Link çıkartılamadı.")
                
                time.sleep(0.3)

            # If it's the last page according to the API, stop
            if page >= data.get('totalPages', max_pages):
                print("\nSon sayfaya ulaşıldı.")
                break

        except Exception as e:
            print(f"Hata oluştu (Sayfa {page}): {e}")
            break

    print(f"\nToplam {total_extracted} link başarıyla çıkartıldı.")

if __name__ == "__main__":
    # Varsayılan olarak 2 sayfa çekelim
    crawl_discover_movies(max_pages=2)
