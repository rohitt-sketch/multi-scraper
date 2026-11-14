from scrapers.vk import check_status

urls = """https://vkvideo.ru/video-220321455_456240099
https://vkvideo.ru/video-228699804_456239621
https://vkvideo.ru/video-108468_456257746"""

print("Checking URLs via VK Internal API... Please wait...")
results = check_status(urls)
for r in results:
    print(f"URL: {r['url']}  -->  Status: {r['status']}")
