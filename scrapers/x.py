import requests
import re
import concurrent.futures

def extract_tweet_id(url):
    # URL se Tweet ID nikalne ke liye Regex
    match = re.search(r'(?:x|twitter)\.com\/\w+\/status\/(\d+)', url)
    return match.group(1) if match else None

def check_x_status(url):
    tweet_id = extract_tweet_id(url)
    if not tweet_id:
        return {"status": "Invalid URL", "url": url, "title": "-", "author": "-", "likes": "-", "views": "-", "date": "-", "subs": "-"}

    api_url = f"https://api.fxtwitter.com/2/status/{tweet_id}"
    headers = {'User-Agent': 'MyMultiScraper/1.0'}
    
    try:
        response = requests.get(api_url, headers=headers, timeout=10)
        data = response.json()

        if data.get('code') == 200:
            tweet = data.get('tweet', {})
            author = tweet.get('author', {})
            
            # Check karein ki media (photo/video) available hai ya nahi
            media_data = tweet.get('media', {})
            media_list = media_data.get('all', []) if media_data else []
            
            # Agar media list khali hai, matlab video/photo disabled hai (copyright ya deletion)
            if not media_list:
                return {
                    "status": "Dead / Media Disabled", 
                    "url": url, 
                    "title": "Media not available", 
                    "author": author.get('screen_name', 'Unknown'),
                    "likes": "-", "views": "-", "date": "-", "subs": "-"
                }

            # Agar media maujood hai toh Active
            return {
                "status": "Active",
                "url": url,
                "title": tweet.get('text', '')[:100],
                "author": author.get('screen_name', 'Unknown'),
                "likes": f"{tweet.get('likes', 0):,}",
                "views": f"{tweet.get('views', 0):,}",
                "date": tweet.get('created_at', '-'),
                "subs": "N/A"
            }
        else:
            return {"status": "Dead / Private", "url": url, "title": "-", "author": "-", "likes": "-", "views": "-", "date": "-", "subs": "-"}
            
    except Exception as e:
        return {"status": f"Error", "url": url, "title": str(e)[:50], "author": "-", "likes": "-", "views": "-", "date": "-", "subs": "-"}

def scrape_data(urls_str):
    url_list = [u.strip() for u in urls_str.split('\n') if u.strip()]
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        return list(executor.map(check_x_status, url_list))

def check_status(urls_str):
    results = scrape_data(urls_str)
    return [{"status": r["status"], "url": r["url"]} for r in results]