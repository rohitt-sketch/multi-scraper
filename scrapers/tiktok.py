import requests
import concurrent.futures
from datetime import datetime

# Number format karne ke liye (e.g. 1,000,000)
def format_number(num):
    try:
        return f"{int(num):,}"
    except (ValueError, TypeError):
        return "0"

# Date format karne ke liye (YYYY-MM-DD)
def format_date(timestamp):
    try:
        if timestamp:
            dt = datetime.fromtimestamp(timestamp)
            return dt.strftime('%Y-%m-%d')
        return "-"
    except:
        return "-"

# Duration format karne ke liye (MM:SS)
def format_duration(seconds):
    try:
        seconds = int(seconds)
        m = seconds // 60
        s = seconds % 60
        return f"{m:02d}:{s:02d}"
    except:
        return "-"

# Error aane par default result
def get_error_result(url, status="Dead / Error"):
    return {
        "status": status,
        "url": url,
        "title": "Not Found or Invalid",
        "author": "-",
        "views": "0",
        "likes": "-",
        "duration": "-",
        "date": "-",
        "subs": "-"
    }

# Ek single URL ko scrape karne ka function
def fetch_tiktok_data(url):
    api_url = f'https://www.tikwm.com/api/?url={url}'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
    }
    
    try:
        response = requests.get(api_url, headers=headers, timeout=10)
        json_data = response.json()
        
        # Check karein ki data valid hai ya nahi
        if json_data and json_data.get('data') and json_data['data'].get('title'):
            d = json_data['data']
            author_name = d.get('author', {}).get('nickname') or d.get('author', {}).get('unique_id') or '-'
            
            return {
                "status": "Active",
                "url": url,
                "title": d.get('title', ''),
                "author": author_name,
                "views": format_number(d.get('play_count', 0)),
                "likes": format_number(d.get('digg_count', 0)),
                "duration": format_duration(d.get('duration', 0)),
                "date": format_date(d.get('create_time')),
                "subs": "N/A"
            }
        else:
            return get_error_result(url, "Dead / Error")
            
    except Exception as e:
        return get_error_result(url, "Dead / Error")

# Full Scrape Function (Frontend 'Full Scrape' button isko call karega)
def scrape_data(urls_str):
    url_list = [u.strip() for u in urls_str.split('\n') if u.strip()]
    if not url_list:
        return []

    # Multithreading use kar rahe hain taaki multiple links jaldi process hon
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(fetch_tiktok_data, url_list))
    
    return results

# Fast Status Check Function (Frontend 'Fast Status Check' button isko call karega)
def check_status(urls_str):
    url_list = [u.strip() for u in urls_str.split('\n') if u.strip()]
    if not url_list:
        return []

    results = []
    # Status check ke liye zyada workers use kar sakte hain
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        data_list = list(executor.map(fetch_tiktok_data, url_list))
        
        for item in data_list:
            # Frontend ko sirf status aur url chahiye is mode me
            results.append({
                "status": item["status"],
                "url": item["url"]
            })
    return results