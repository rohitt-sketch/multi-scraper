import json
import io
import csv

def extract_text(msg):
    """Telegram text kabhi string hota hai, kabhi entities ka list."""
    text = msg.get("text", "")
    if isinstance(text, list):
        parts = []
        for item in text:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and "text" in item:
                parts.append(item["text"])
        return "".join(parts)
    return str(text)

def parse_telegram_json(file_contents):
    """
    Uploaded JSON file se data nikalta hai.
    Returns: (headers, rows, error)
    """
    try:
        data = json.loads(file_contents)
    except Exception as e:
        return None, None, f"Invalid JSON file: {str(e)}"

    # Check karein ki ye Telegram export hai ya simple JSON
    messages = []
    if isinstance(data, dict) and "messages" in data:
        messages = data["messages"]
    elif isinstance(data, list):
        messages = data
    else:
        return None, None, "JSON format not recognized. Please upload Telegram export JSON."

    if not messages:
        return None, None, "No messages found in the JSON."

    # Headers define karein
    headers = ["ID", "Date", "From", "Text"]
    
    # Check karein ki kya extra fields hain (jaise media)
    has_media = any("media_type" in m for m in messages)
    has_reply = any("reply_to_message_id" in m for m in messages)
    
    if has_media: headers.append("Media Type")
    if has_reply: headers.append("Reply To")

    rows = []
    for msg in messages:
        if not isinstance(msg, dict): continue
        
        row = [
            msg.get("id", ""),
            msg.get("date", "").replace("T", " ")[:19],
            msg.get("from", "Unknown"),
            extract_text(msg)
        ]
        
        if has_media:
            row.append(msg.get("media_type", ""))
        if has_reply:
            row.append(msg.get("reply_to_message_id", ""))

        rows.append(row)

    return headers, rows, None

def convert_to_csv(headers, rows):
    """Data ko CSV format me convert karta hai download ke liye."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)
    return output.getvalue()
