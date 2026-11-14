import yt_dlp
import concurrent.futures

def check_vk_status(url):
    # yt-dlp VK ke liye sabse robust extractor hai
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'simulate': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info:
                return {"status": "Active", "url": url}
            else:
                return {"status": "Dead / Private", "url": url}
                
    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e).lower()
        # Agar video delete/private hai toh ye errors aate hain
        if any(x in error_msg for x in ["deleted", "not found", "unavailable", "private", "removed"]):
            return {"status": "Dead / Private", "url": url}
        # Agar network error hai
        elif any(x in error_msg for x in ["connection reset", "aborted", "timed out"]):
            return {"status": "Error: Network Blocked", "url": url}
        else:
            return {"status": "Dead / Private", "url": url}
            
    except Exception as e:
        return {"status": f"Error: {str(e)}", "url": url}

def check_status(urls_str):
    url_list = [u.strip() for u in urls_str.split('\n') if u.strip()]
    # Ek baar me sirf 1 request, taaki Render par bhi VK block na kare
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return list(executor.map(check_vk_status, url_list))

def scrape_data(urls_str):
    return check_status(urls_str)
