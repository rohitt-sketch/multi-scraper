from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import sqlite3
import os
from scrapers import youtube, tiktok

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Yahan apna asli email daalo, sirf yahi admin hoga
ADMIN_EMAIL = "joshirohitt@gmail.com" 

# --- Database Setup ---
def init_db():
    # DHYAN DEIN: Database ka naam badal kar scraper_v2.db kar diya gaya hai
    conn = sqlite3.connect('scraper_v2.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (email TEXT PRIMARY KEY, password TEXT, status TEXT DEFAULT 'pending')''')
    conn.commit()
    conn.close()

init_db()

# 1. Login/Register Page (Home)
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    if request.cookies.get("user_session"):
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse(request=request, name="login.html")

# 2. Register Route
@app.post("/register")
async def register(request: Request, email: str = Form(...), password: str = Form(...)):
    conn = sqlite3.connect('scraper_v2.db')
    c = conn.cursor()
    try:
        status = 'approved' if email == ADMIN_EMAIL else 'pending'
        c.execute("INSERT INTO users (email, password, status) VALUES (?, ?, ?)", (email, password, status))
        conn.commit()
        conn.close()
        
        if status == 'approved':
            response = RedirectResponse(url="/dashboard", status_code=303)
            response.set_cookie(key="user_session", value=email, httponly=True)
            return response
        else:
            return RedirectResponse(url="/?error=Account ban gaya! Ab Admin approval ka wait karein.", status_code=303)
            
    except sqlite3.IntegrityError:
        conn.close()
        return RedirectResponse(url="/?error=Yeh email pehle se registered hai!", status_code=303)

# 3. Login Route
@app.post("/login")
async def login(request: Request, email: str = Form(...), password: str = Form(...)):
    conn = sqlite3.connect('scraper_v2.db')
    c = conn.cursor()
    c.execute("SELECT password, status FROM users WHERE email = ?", (email,))
    user = c.fetchone()
    conn.close()

    if user and user[0] == password:
        status = user[1]
        if status == 'pending':
            return RedirectResponse(url="/?error=Aapka account abhi approve nahi hua hai. Admin se sampark karein.", status_code=303)
        
        response = RedirectResponse(url="/dashboard", status_code=303)
        response.set_cookie(key="user_session", value=email, httponly=True)
        return response
    else:
        return RedirectResponse(url="/?error=Galat email ya password!", status_code=303)

# 4. Secure Dashboard (Admin Panel)
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    user_email = request.cookies.get("user_session")
    if not user_email:
        return RedirectResponse(url="/", status_code=303)
    
    return templates.TemplateResponse(request=request, name="dashboard.html", context={"user": user_email, "is_admin": user_email == ADMIN_EMAIL})

# 5. Logout Route
@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("user_session")
    return response

# 6. ADMIN APPROVAL PAGE
@app.get("/admin/approvals", response_class=HTMLResponse)
async def admin_approvals(request: Request):
    user_email = request.cookies.get("user_session")
    if user_email != ADMIN_EMAIL:
        return RedirectResponse(url="/dashboard", status_code=303)
        
    conn = sqlite3.connect('scraper_v2.db')
    c = conn.cursor()
    c.execute("SELECT email, status FROM users WHERE email != ?", (ADMIN_EMAIL,))
    all_users = c.fetchall()
    conn.close()
    
    return templates.TemplateResponse(request=request, name="admin.html", context={"users": all_users})

# 7. APPROVE USER ACTION
@app.post("/admin/approve")
async def approve_user(request: Request, target_email: str = Form(...)):
    user_email = request.cookies.get("user_session")
    if user_email != ADMIN_EMAIL:
        return RedirectResponse(url="/dashboard", status_code=303)
        
    conn = sqlite3.connect('scraper_v2.db')
    c = conn.cursor()
    c.execute("UPDATE users SET status = 'approved' WHERE email = ?", (target_email,))
    conn.commit()
    conn.close()
    
    return RedirectResponse(url="/admin/approvals", status_code=303)

# ==========================================
# SCRAPER API ROUTES
# ==========================================
@app.post("/scrape_youtube")
async def api_scrape_youtube(urls: str = Form(...)):
    return {"results": youtube.scrape_data(urls)}

@app.post("/scrape_tiktok")
async def api_scrape_tiktok(urls: str = Form(...)):
    return {"results": tiktok.scrape_data(urls)}

@app.post("/check_status")
async def api_check_status(urls: str = Form(...)):
    return {"results": tiktok.check_status(urls)}