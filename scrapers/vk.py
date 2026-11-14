import requests
import re
import concurrent.futures

def parse_vk_url(url):
    # URL se oid aur id nikalne ka regex (vk.com, vkvideo.ru sabke liye)
    match = re.search(r'video(-?\d+)_(\d+)', url, re.IGNORECASE)
    if match: return match.group(1), match.group(2)
    
    match = re.search(r'oid=(-?\d+)&id=(\d+)', url, re.IGNORECASE)
    if match: return match.group(1), match.group(2)
    
    return None, None

def fetch_vk_status(url):
    oid, vid = parse_vk_url(url)
    if not oid:
        return {"status": "Invalid URL", "url": url}

    # Embed URL check karne ke liye sabse best hota hai
    embed_url = f"https://vk.com/video_ext.php?oid={oid}&id={vid}&hd=2"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9,ru;q=0.8'
    }
    
    try:
        resp = requests.get(embed_url, headers=headers, timeout=10)
        
        if resp.status_code != 200:
            return {"status": f"Dead / HTTP {resp.status_code}", "url": url}
            
        html = resp.text
        
        # VK ke naye aur strict dead markers
        dead_markers = [
            'This video is unavailable', 'Видео недоступно', 'video_ext_msg', 
            'The video is unavailable', 'Video deleted', 'Видео удалено',
            'video_deleted', 'video_unavailable', 'error_msg'
        ]
        
        for marker in dead_markers:
            if marker in html:
                return {"status": "Dead / Private", "url": url}
                
        # Title check (Agar title empty ya generic "VK Video" hai toh dead hai)
        title_match = re.search(r'<meta property="og:title" content="([^"]*)"', html)
        title = title_match.group(1) if title_match else ""
        
        if title in ["VK Video", "Video deleted", "Видео удалено", ""]:
            return {"status": "Dead / Private", "url": url}
            
        return {"status": "Active", "url": url}

    except Exception as e:
        return {"status": "Error", "url": url}

def check_status(urls_str):
    url_list = [u.strip() for u in urls_str.split('\n') if u.strip()]
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        return list(executor.map(fetch_vk_status, url_list))

def scrape_data(urls_str):
    return check_status(urls_str)
