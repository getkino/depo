import requests
import re
from bs4 import BeautifulSoup
import json
import time
import base64
import os

def decode_hex_string(hex_string):
    """Hex encoded string'i decode eder"""
    try:
        clean_hex = hex_string.replace('\\x', '')
        decoded = bytes.fromhex(clean_hex).decode('utf-8')
        return decoded
    except:
        return None

def extract_video_info(content):
    """Video başlığı ve açıklamasını çıkarır"""
    video_info = {}
    jwsetup_patterns = [
        r'jwSetup\s*=\s*{([^}]+)}',
        r'var\s+jwSetup\s*=\s*{([^}]+)}'
    ]
    for pattern in jwsetup_patterns:
        match = re.search(pattern, content, re.DOTALL)
        if match:
            jwsetup_content = match.group(1)
            title_match = re.search(r'title:\s*["\']([^"\']+)["\']', jwsetup_content)
            if title_match:
                video_info['title'] = title_match.group(1)
            desc_match = re.search(r'description:\s*["\']([^"\']+)["\']', jwsetup_content)
            if desc_match:
                video_info['description'] = desc_match.group(1)
            break
    if not video_info.get('title'):
        title_patterns = [
            r'title:\s*["\']([^"\']+)["\']',
            r'"title":\s*"([^"]+)"',
            r"'title':\s*'([^']+)'"
        ]
        for pattern in title_patterns:
            match = re.search(pattern, content)
            if match:
                video_info['title'] = match.group(1)
                break
    if not video_info.get('description'):
        desc_patterns = [
            r'description:\s*["\']([^"\']+)["\']',
            r'"description":\s*"([^"]+)"',
            r"'description':\s*'([^']+)'"
        ]
        for pattern in desc_patterns:
            match = re.search(pattern, content)
            if match:
                video_info['description'] = match.group(1)
                break
    return video_info

def find_m3u8_url(page_url):
    """Verilen diziyiizle.com sayfasından m3u8 URL'sini bulur"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'tr-TR,tr;q=0.8,en-US;q=0.5,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate',
            'Referer': 'https://diziyiizle.com/',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        response = requests.get(page_url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        scripts = soup.find_all('script')
        m3u8_urls = []
        subtitle_urls = []
        embed_urls = []
        video_info = {}
        for script in scripts:
            if script.string:
                script_content = script.string
                m3u8_pattern = r'https://[^\s"\']*\.m3u8[^\s"\']*'
                matches = re.findall(m3u8_pattern, script_content)
                for match in matches:
                    if match not in m3u8_urls:
                        m3u8_urls.append(match)
                video_url_patterns = [
                    r'videoUrl\s*=\s*["\']([^"\']+)["\']',
                    r'src:\s*["\']([^"\']*vidlax[^"\']*)["\']',
                    r'["\']([^"\']*vidlax\.xyz[^"\']*)["\']'
                ]
                for pattern in video_url_patterns:
                    video_matches = re.findall(pattern, script_content)
                    for video_url in video_matches:
                        clean_url = video_url.replace('\\/', '/')
                        if clean_url not in embed_urls:
                            embed_urls.append(clean_url)
                            print(f"📺 Embed URL bulundu: {clean_url}")
        page_m3u8 = re.findall(r'https://[^\s"\']*\.m3u8[^\s"\']*', response.text)
        m3u8_urls.extend(page_m3u8)
        vidlax_pattern = r'https://vidlax\.xyz/[^\s"\']*\.m3u8[^\s"\']*'
        vidlax_matches = re.findall(vidlax_pattern, response.text)
        m3u8_urls.extend(vidlax_matches)
        for video_url in embed_urls:
            print(f"🔍 Embed URL kontrol ediliyor: {video_url}")
            try:
                time.sleep(1)
                embed_headers = headers.copy()
                embed_headers['Referer'] = page_url
                embed_response = requests.get(video_url, headers=embed_headers, timeout=10)
                embed_response.raise_for_status()
                print(f"📄 Embed sayfa içeriği alındı, boyut: {len(embed_response.text)} karakter")
                video_info = extract_video_info(embed_response.text)
                if video_info:
                    title = video_info.get('title', 'Bilinmiyor')
                    description = video_info.get('description', 'Bilinmiyor')
                    print(f"🎬 Video Başlığı: {title}")
                    print(f"📝 Video Açıklaması: {description}")
                    if title != 'Bilinmiyor' and description != 'Bilinmiyor':
                        print(f"🎯 Tam Başlık: {title} - {description}")
                hex_patterns = [
                    r'"file":\s*"(\\x[0-9a-fA-F\\x]+)"',
                    r"'file':\s*'(\\x[0-9a-fA-F\\x]+)'",
                    r'(\\x[0-9a-fA-F\\x]+\.m3u8[0-9a-fA-F\\x]*)',
                    r'"(\\x2e[0-9a-fA-F\\x]+\.m3u8[0-9a-fA-F\\x]*)"'
                ]
                for pattern in hex_patterns:
                    hex_matches = re.findall(pattern, embed_response.text)
                    for hex_match in hex_matches:
                        decoded_url = decode_hex_string(hex_match)
                        if decoded_url and '.m3u8' in decoded_url:
                            if decoded_url.startswith('../'):
                                full_url = 'https://vidlax.xyz' + decoded_url[2:]
                            elif decoded_url.startswith('/'):
                                full_url = 'https://vidlax.xyz' + decoded_url
                            else:
                                full_url = 'https://vidlax.xyz/' + decoded_url
                            if full_url not in m3u8_urls:
                                m3u8_urls.append(full_url)
                                print(f"🎯 HEX DECODE - m3u8 bulundu: {full_url}")
                subtitle_patterns = [
                    r'"file":\s*"([^"]*\.vtt[^"]*)"',
                    r"'file':\s*'([^']*\.vtt[^']*)'",
                    r'tracks\s*=\s*\[([^\]]+)\]',
                    r'"file"\s*:\s*"([^"]*subtitles[^"]*\.vtt[^"]*)"',
                    r'\.\.\/upload\/[^"\']*\/subtitles\/[^"\']*\.vtt'
                ]
                for pattern in subtitle_patterns:
                    subtitle_matches = re.findall(pattern, embed_response.text)
                    for match in subtitle_matches:
                        if '.vtt' in match:
                            if match.startswith('../'):
                                subtitle_full_url = 'https://vidlax.xyz' + match[2:]
                            elif match.startswith('/'):
                                subtitle_full_url = 'https://vidlax.xyz' + match
                            else:
                                subtitle_full_url = 'https://vidlax.xyz/' + match
                            if subtitle_full_url not in subtitle_urls:
                                subtitle_urls.append(subtitle_full_url)
                tracks_pattern = r'jwSetup\.tracks\s*=\s*(\[[^\]]+\])'
                tracks_matches = re.findall(tracks_pattern, embed_response.text)
                for tracks_data in tracks_matches:
                    try:
                        tracks_clean = tracks_data.replace('\\/', '/')
                        tracks_obj = json.loads(tracks_clean)
                        for track in tracks_obj:
                            if 'file' in track and '.vtt' in track['file']:
                                file_path = track['file']
                                if file_path.startswith('../'):
                                    subtitle_full_url = 'https://vidlax.xyz' + file_path[2:]
                                elif file_path.startswith('/'):
                                    subtitle_full_url = 'https://vidlax.xyz' + file_path
                                else:
                                    subtitle_full_url = 'https://vidlax.xyz/' + file_path
                                if subtitle_full_url not in subtitle_urls:
                                    subtitle_urls.append(subtitle_full_url)
                    except:
                        pass
                embed_m3u8_patterns = [
                    r'https://[^\s"\']*\.m3u8[^\s"\']*',
                    r'"file":\s*"([^"]*\.m3u8[^"]*)"',
                    r"'file':\s*'([^']*\.m3u8[^']*)'",
                    r'source:\s*"([^"]*\.m3u8[^"]*)"',
                    r'src:\s*"([^"]*\.m3u8[^"]*)"'
                ]
                for pattern in embed_m3u8_patterns:
                    embed_matches = re.findall(pattern, embed_response.text)
                    for match in embed_matches:
                        clean_match = match.replace('\\/', '/')
                        if clean_match not in m3u8_urls:
                            m3u8_urls.append(clean_match)
                            print(f"✓ Embed'de m3u8 bulundu: {clean_match}")
                js_vars = re.findall(r'var\s+\w+\s*=\s*["\']([^"\']*\.m3u8[^"\']*)["\']', embed_response.text)
                for var_url in js_vars:
                    clean_var = var_url.replace('\\/', '/')
                    if clean_var not in m3u8_urls:
                        m3u8_urls.append(clean_var)
                        print(f"✓ JavaScript değişkeninde m3u8 bulundu: {clean_var}")
                if 'atob' in embed_response.text or 'base64' in embed_response.text.lower():
                    print("Base64 kodlama tespit edildi, içerik analiz ediliyor...")
            except Exception as e:
                print(f"❌ Embed URL kontrol hatası ({video_url}): {e}")
        unique_m3u8_urls = list(set(m3u8_urls))
        unique_subtitle_urls = list(set(subtitle_urls))
        return unique_m3u8_urls, unique_subtitle_urls, embed_urls, video_info
    except Exception as e:
        print(f"Hata oluştu: {e}")
        return [], [], [], {}

def analyze_vidlax_direct(embed_url):
    """Vidlax embed URL'sini doğrudan analiz eder"""
    print(f"\n🔍 Vidlax direkt analizi: {embed_url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Referer': 'https://diziyiizle.com/',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
    try:
        response = requests.get(embed_url, headers=headers, timeout=15)
        response.raise_for_status()
        content = response.text
        print(f"📄 Sayfa içeriği alındı: {len(content)} karakter")
        found_urls = []
        found_subtitles = []
        video_info = extract_video_info(content)
        if video_info:
            title = video_info.get('title', 'Bilinmiyor')
            description = video_info.get('description', 'Bilinmiyor')
            print(f"🎬 Video Başlığı: {title}")
            print(f"📝 Video Açıklaması: {description}")
            if title != 'Bilinmiyor' and description != 'Bilinmiyor':
                print(f"🎯 Tam Başlık: {title} - {description}")
        hex_pattern = r'"file":\s*"(\\x[0-9a-fA-F\\x]+)"'
        hex_matches = re.findall(hex_pattern, content)
        for hex_string in hex_matches:
            print(f"🔍 Hex string bulundu: {hex_string[:50]}...")
            decoded = decode_hex_string(hex_string)
            if decoded:
                print(f"🔓 Hex decode edildi: {decoded}")
                if decoded.startswith('../'):
                    full_url = 'https://vidlax.xyz' + decoded[2:]
                elif decoded.startswith('/'):
                    full_url = 'https://vidlax.xyz' + decoded
                else:
                    full_url = 'https://vidlax.xyz/' + decoded
                found_urls.append(full_url)
                print(f"🎯 TAM URL: {full_url}")
        tracks_pattern = r'jwSetup\.tracks\s*=\s*(\[[^\]]+\])'
        tracks_matches = re.findall(tracks_pattern, content)
        for tracks_data in tracks_matches:
            print(f"📋 jwSetup.tracks bulundu: {tracks_data[:100]}...")
            try:
                tracks_clean = tracks_data.replace('\\/', '/').replace('\\u', '\\u')
                tracks_obj = json.loads(tracks_clean)
                for track in tracks_obj:
                    if 'file' in track:
                        file_path = track['file']
                        if file_path.startswith('../'):
                            subtitle_url = 'https://vidlax.xyz' + file_path[2:]
                        elif file_path.startswith('/'):
                            subtitle_url = 'https://vidlax.xyz' + file_path
                        else:
                            subtitle_url = 'https://vidlax.xyz/' + file_path
                        found_subtitles.append({
                            'url': subtitle_url,
                            'label': track.get('label', 'Bilinmiyor'),
                            'language': track.get('language', 'Bilinmiyor'),
                            'kind': track.get('kind', 'captions')
                        })
                        print(f"💬 Altyazı bulundu:")
                        print(f"   📎 URL: {subtitle_url}")
                        print(f"   📝 Label: {track.get('label', 'Bilinmiyor')}")
                        print(f"   🌐 Language: {track.get('language', 'Bilinmiyor')}")
                        print(f"   📋 Kind: {track.get('kind', 'captions')}")
            except Exception as e:
                print(f"   ❌ JSON parse hatası: {e}")
        decoded_urls = decode_base64_strings(content)
        found_urls.extend(decoded_urls)
        if found_urls:
            print("🎯 Bulunan m3u8 URL'leri:")
            for url in found_urls:
                print(f"   ✓ {url}")
        else:
            print("❌ m3u8 URL'si bulunamadı")
        return found_urls, found_subtitles, video_info
    except Exception as e:
        print(f"Vidlax analiz hatası: {e}")
        return [], [], {}

def decode_base64_strings(content):
    """Base64 kodlanmış stringleri decode eder"""
    base64_patterns = [
        r'atob\(["\']([A-Za-z0-9+/=]+)["\']',
        r'["\']([A-Za-z0-9+/=]{20,})["\']'
    ]
    decoded_strings = []
    for pattern in base64_patterns:
        matches = re.findall(pattern, content)
        for match in matches:
            try:
                decoded = base64.b64decode(match).decode('utf-8')
                if '.m3u8' in decoded:
                    decoded_strings.append(decoded)
                    print(f"🔓 Base64 decode edildi: {decoded}")
            except:
                pass
    return decoded_strings

def extract_episode_links(series_url):
    """Dizi ana sayfasından tüm bölüm linklerini, posteri, backdrop ve grubu çıkarır"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'tr-TR,tr;q=0.8,en-US;q=0.5,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate',
            'Referer': 'https://diziyiizle.com/',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        response = requests.get(series_url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        episode_links = []
        poster_url = None
        backdrop_url = None
        img_poster = soup.select_one('img[src*="series_poster_"]') or soup.select_one('div.overflow-hidden img')
        if img_poster and img_poster.get('src'):
            poster_url = img_poster['src'].strip()
        img_backdrop = soup.select_one('img[src*="series_backdrop_"]') or soup.select_one('div.absolute.inset-0 img') or soup.select_one('div.relative img')
        if img_backdrop and img_backdrop.get('src'):
            backdrop_url = img_backdrop['src'].strip()
        if (not poster_url or poster_url.startswith('data:image')) and soup.find('meta', property='og:image'):
            meta_img = soup.find('meta', property='og:image')
            if meta_img and meta_img.get('content') and not meta_img['content'].startswith('data:image'):
                poster_url = meta_img['content'].strip()
        if (not backdrop_url or backdrop_url.startswith('data:image')) and soup.find('meta', property='og:image'):
            meta_img = soup.find('meta', property='og:image')
            if meta_img and meta_img.get('content') and not meta_img['content'].startswith('data:image'):
                backdrop_url = meta_img['content'].strip()
        group_name = None
        h4 = soup.find(lambda tag: tag.name == 'h4' and 'Platform' in tag.get_text())
        if h4:
            sibling = h4.find_next_sibling()
            if sibling:
                span_tag = sibling.select_one('span') or sibling.find('span')
                if span_tag:
                    group_name = ' '.join(span_tag.get_text(strip=True).split())
        if not group_name:
            span_fallback = soup.select_one('div.flex.flex-wrap.gap-2 span') or soup.select_one('a[href*="/platform/"]')
            if span_fallback:
                group_name = ' '.join(span_fallback.get_text(strip=True).split())
        episode_patterns = [
            'a[href*="/sezon-"][href*="-bolum/"]',
            'a[href*="-bolum/"]',
        ]
        for pattern in episode_patterns:
            links = soup.select(pattern)
            for link in links:
                href = link.get('href')
                if href:
                    if href.startswith('/'):
                        full_url = 'https://diziyiizle.com' + href
                    elif href.startswith('http'):
                        full_url = href
                    else:
                        full_url = 'https://diziyiizle.com/' + href
                    if full_url not in episode_links and 'bolum' in full_url:
                        episode_links.append(full_url)
                        episode_text = link.get_text(strip=True)
                        print(f"📺 Bölüm bulundu: {episode_text} - {full_url}")
        print(f"\n📊 Toplam {len(episode_links)} bölüm bulundu")
        return episode_links, poster_url, backdrop_url, group_name
    except Exception as e:
        print(f"❌ Dizi sayfası analiz hatası: {e}")
        return [], None, None, None

def create_m3u_playlist(entries, series_url):
    """m3u8 playlist dosyası oluşturur"""
    try:
        series_name = series_url.split('/')[-2] if series_url.endswith('/') else series_url.split('/')[-1]
        filename = f"{series_name}_playlist.m3u"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("#EXTM3U\n")
            f.write(f"# {series_name} - Tüm Bölümler\n")
            f.write(f"# Oluşturma Tarihi: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# Toplam Bölüm: {len(entries)}\n")
            f.write(f"# Dizi URL: {series_url}\n")
            if entries and entries[0].get('poster'):
                f.write(f"# Poster: {entries[0]['poster']}\n")
            if entries and entries[0].get('backdrop'):
                f.write(f"# Backdrop: {entries[0]['backdrop']}\n")
            if entries and entries[0].get('group'):
                f.write(f"# Grup: {entries[0]['group']}\n")
            f.write("\n")
            for entry in entries:
                tvg = entry.get('poster') or entry.get('backdrop') or ''
                attrs = []
                if tvg:
                    attrs.append(f'tvg-logo="{tvg}"')
                if entry.get('group'):
                    attrs.append(f'group-title="{entry["group"]}"')
                attr_str = ' '.join(attrs)
                if attr_str:
                    f.write(f'#EXTINF:-1 {attr_str},{entry["title"]}\n')
                else:
                    f.write(f'#EXTINF:-1,{entry["title"]}\n')
                f.write(f"{entry['url']}\n\n")
        print(f"📁 Playlist dosyası oluşturuldu: {filename}")
    except Exception as e:
        print(f"❌ Playlist oluşturma hatası: {e}")

def create_individual_series_playlist(entries, series_url):
    """Her dizi için ayrı playlist dosyası oluşturur"""
    try:
        series_name = series_url.split('/')[-2] if series_url.endswith('/') else series_url.split('/')[-1]
        series_name = series_name.replace('dizi/', '').replace('-', '_')
        filename = f"playlists/{series_name}_playlist.m3u"
        os.makedirs('playlists', exist_ok=True)
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("#EXTM3U\n")
            f.write(f"# {series_name} - Tüm Bölümler\n")
            f.write(f"# Oluşturma Tarihi: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# Toplam Bölüm: {len(entries)}\n")
            f.write(f"# Dizi URL: {series_url}\n")
            if entries and entries[0].get('poster'):
                f.write(f"# Poster: {entries[0]['poster']}\n")
            if entries and entries[0].get('backdrop'):
                f.write(f"# Backdrop: {entries[0]['backdrop']}\n")
            if entries and entries[0].get('group'):
                f.write(f"# Grup: {entries[0]['group']}\n")
            f.write("\n")
            for entry in entries:
                tvg = entry.get('poster') or entry.get('backdrop') or ''
                attrs = []
                if tvg:
                    attrs.append(f'tvg-logo="{tvg}"')
                if entry.get('group'):
                    attrs.append(f'group-title="{entry["group"]}"')
                attr_str = ' '.join(attrs)
                if attr_str:
                    f.write(f'#EXTINF:-1 {attr_str},{entry["title"]}\n')
                else:
                    f.write(f'#EXTINF:-1,{entry["title"]}\n')
                f.write(f"{entry['url']}\n\n")
        print(f"      📁 Dizi playlist: {filename}")
    except Exception as e:
        print(f"      ❌ Dizi playlist hatası: {e}")

def create_master_playlist(entries):
    """Tüm diziler için master playlist dosyası oluşturur"""
    try:
        filename = "master_all_series_playlist.m3u"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("#EXTM3U\n")
            f.write(f"# TÜM DİZİLER - MASTER PLAYLIST\n")
            f.write(f"# Oluşturma Tarihi: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# Toplam Bölüm: {len(entries)}\n\n")
            series_groups = {}
            for entry in entries:
                series_url = entry['series_url']
                series_name = series_url.split('/')[-2] if series_url.endswith('/') else series_url.split('/')[-1]
                if series_name not in series_groups:
                    series_groups[series_name] = []
                series_groups[series_name].append(entry)
            for series_name, series_entries in series_groups.items():
                f.write(f"\n# === {series_name.upper()} === ({len(series_entries)} bölüm)\n")
                if series_entries and series_entries[0].get('poster'):
                    f.write(f"# Poster: {series_entries[0]['poster']}\n")
                if series_entries and series_entries[0].get('backdrop'):
                    f.write(f"# Backdrop: {series_entries[0]['backdrop']}\n")
                if series_entries and series_entries[0].get('group'):
                    f.write(f"# Grup: {series_entries[0]['group']}\n")
                for entry in series_entries:
                    tvg = entry.get('poster') or entry.get('backdrop') or ''
                    attrs = []
                    if tvg:
                        attrs.append(f'tvg-logo="{tvg}"')
                    if entry.get('group'):
                        attrs.append(f'group-title="{entry["group"]}"')
                    attr_str = ' '.join(attrs)
                    if attr_str:
                        f.write(f'#EXTINF:-1 {attr_str},{entry["title"]}\n')
                    else:
                        f.write(f'#EXTINF:-1,{entry["title"]}\n')
                    f.write(f"{entry['url']}\n\n")
        print(f"\n📁 Master playlist oluşturuldu: {filename}")
    except Exception as e:
        print(f"❌ Master playlist hatası: {e}")

def find_m3u8_url_simple(page_url):
    """Basit m3u8 bulucu wrapper"""
    try:
        result = find_m3u8_url(page_url)
        if result and isinstance(result, tuple):
            m3u8_urls, subtitle_urls, embed_urls, video_info = result
        else:
            m3u8_urls, subtitle_urls, embed_urls, video_info = [], [], [], {}
        if m3u8_urls:
            return m3u8_urls, video_info
        for embed in embed_urls:
            try:
                if 'vidlax' in embed or 'vidlax.xyz' in embed:
                    found, subs, vinfo = analyze_vidlax_direct(embed)
                    if vinfo and not video_info:
                        video_info = vinfo
                    for u in found:
                        if u not in m3u8_urls:
                            m3u8_urls.append(u)
                else:
                    try:
                        found, subs, vinfo = analyze_vidlax_direct(embed)
                        if vinfo and not video_info:
                            video_info = vinfo
                        for u in found:
                            if u not in m3u8_urls:
                                m3u8_urls.append(u)
                    except:
                        pass
            except Exception:
                continue
            if m3u8_urls:
                return m3u8_urls, video_info
        try:
            found, subs, vinfo = analyze_vidlax_direct(page_url)
            if vinfo and not video_info:
                video_info = vinfo
            for u in found:
                if u not in m3u8_urls:
                    m3u8_urls.append(u)
        except:
            pass
        return m3u8_urls, video_info
    except Exception as e:
        print(f"find_m3u8_url_simple hata: {e}")
        return [], {}

def extract_all_series_links(series_page_url):
    """Tüm dizilerin linklerini çıkarır"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'tr-TR,tr;q=0.8,en-US;q=0.5,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate',
            'Referer': 'https://diziyiizle.com/',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        response = requests.get(series_page_url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        series_links = []
        # Dizi linklerini bul (genel pattern'ler)
        series_patterns = [
            'a[href*="/dizi/"]',
            'a[href*="/series/"]',
            'a[href*="/show/"]'
        ]
        for pattern in series_patterns:
            links = soup.select(pattern)
            for link in links:
                href = link.get('href')
                if href and 'bolum' not in href:  # Bölüm linklerini hariç tut
                    if href.startswith('/'):
                        full_url = 'https://diziyiizle.com' + href
                    elif href.startswith('http'):
                        full_url = href
                    else:
                        full_url = 'https://diziyiizle.com/' + href
                    if full_url not in series_links:
                        series_links.append(full_url)
                        print(f"📺 Dizi bulundu: {full_url}")
        # Sayfalamayı kontrol et
        pagination = soup.select('a[href*="/page/"]')
        for page_link in pagination:
            page_href = page_link.get('href')
            if page_href:
                if page_href.startswith('/'):
                    page_url = 'https://diziyiizle.com' + page_href
                else:
                    page_url = page_href
                try:
                    page_response = requests.get(page_url, headers=headers)
                    page_response.raise_for_status()
                    page_soup = BeautifulSoup(page_response.text, 'html.parser')
                    for pattern in series_patterns:
                        links = page_soup.select(pattern)
                        for link in links:
                            href = link.get('href')
                            if href and 'bolum' not in href:
                                if href.startswith('/'):
                                    full_url = 'https://diziyiizle.com' + href
                                elif href.startswith('http'):
                                    full_url = href
                                else:
                                    full_url = 'https://diziyiizle.com/' + href
                                if full_url not in series_links:
                                    series_links.append(full_url)
                                    print(f"📺 Dizi bulundu (sayfa): {full_url}")
                except Exception as e:
                    print(f"❌ Sayfalamada hata: {page_url} - {e}")
        print(f"\n📊 Toplam {len(series_links)} dizi bulundu")
        return series_links
    except Exception as e:
        print(f"❌ Dizi listesi çıkarım hatası: {e}")
        return []

def process_all_series(series_page_url, max_series=None):
    """Tüm dizileri işler"""
    try:
        print(f"🌟 PROCESS ALL: {series_page_url}")
        series_links = extract_all_series_links(series_page_url)
        if not series_links:
            print("❌ Hiç dizi bulunamadı.")
            return
        if max_series and isinstance(max_series, int):
            series_links = series_links[:max_series]
        all_entries = []
        for idx, series_url in enumerate(series_links, 1):
            print(f"\n{'='*60}")
            print(f"🎬 [{idx}/{len(series_links)}] İşleniyor: {series_url}")
            if series_url == "https://diziyiizle.com/dizi/":
                print("   ❌ Kategori sayfası atlandı")
                continue
            try:
                ep_links, poster, backdrop, group = extract_episode_links(series_url)
                if not ep_links:
                    print("   ❌ Bu dizide bölüm bulunamadı")
                    continue
                series_entries = []
                for j, ep in enumerate(ep_links, 1):
                    print(f"   🔍 [{j}/{len(ep_links)}] Bölüm: {ep}")
                    try:
                        m3u8s, vinfo = find_m3u8_url_simple(ep)
                        if m3u8s:
                            title = vinfo.get('title', 'Bilinmiyor') if isinstance(vinfo, dict) else 'Bilinmiyor'
                            desc = vinfo.get('description', '') if isinstance(vinfo, dict) else ''
                            if title != 'Bilinmiyor' and desc:
                                ep_title = f"{title} - {desc}"
                            elif title != 'Bilinmiyor':
                                ep_title = title
                            else:
                                parts = ep.rstrip('/').split('/')
                                ep_title = parts[-1] if parts else f"Bölüm {j}"
                            for u in m3u8s:
                                entry = {
                                    'title': ep_title,
                                    'url': u,
                                    'episode_url': ep,
                                    'series_url': series_url,
                                    'poster': poster,
                                    'backdrop': backdrop,
                                    'group': group
                                }
                                series_entries.append(entry)
                                all_entries.append(entry)
                            print(f"      ✅ {ep_title} - {len(m3u8s)} m3u8")
                        else:
                            print("      ❌ m3u8 bulunamadı")
                    except Exception as e:
                        print(f"      ❌ Bölüm hatası: {e}")
                    if j % 5 == 0:
                        time.sleep(1)
                if series_entries:
                    create_individual_series_playlist(series_entries, series_url)
                    print(f"   ✅ Dizi tamamlandı: {len(series_entries)} m3u8 eklendi")
                else:
                    print("   ❌ Bu dizi için hiç m3u8 bulunamadı")
            except Exception as e:
                print(f"   ❌ Dizi hatası: {e}")
            time.sleep(1.5)
        if all_entries:
            create_master_playlist(all_entries)
            print(f"\n📁 Tüm diziler için master playlist oluşturuldu ({len(all_entries)} item).")
        else:
            print("\n❌ Hiç m3u8 bulunamadı, master playlist oluşturulmadı.")
    except Exception as e:
        print(f"❌ process_all_series hata: {e}")

def main():
    # Tüm diziler sayfası URL'si
    all_series_url = "https://diziyiizle.com/?post_type=series"
    max_series_limit = None
    print("🚀 TÜM DİZİLERİN M3U8'LERİ TOPLANIYOR")
    print("⚡ FULL MODE: Tüm diziler işlenecek!")
    print("⏰ Bu işlem uzun sürebilir...")
    process_all_series(all_series_url, max_series=max_series_limit)

if __name__ == "__main__":
    main()