from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import sqlite3
import os

# Apne scraper imports yahan add karo (agar pehle se nahi hain)
from scrapers import youtube, tiktok 

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# --- Database Setup ---
def init_db():
    conn = sqlite3.connect('scraper.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (email TEXT PRIMARY KEY, password TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- Routes ---

# 1. Login/Register Page (Home)
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    if request.cookies.get("user_session"):
        return RedirectResponse(url="/dashboard", status_code=303)
    # NAYA SYNTAX
    return templates.TemplateResponse(request=request, name="login.html")

# 2. Register Route
@app.post("/register")
async def register(request: Request, email: str = Form(...), password: str = Form(...)):
    conn = sqlite3.connect('scraper.db')
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (email, password) VALUES (?, ?)", (email, password))
        conn.commit()
        conn.close()
        response = RedirectResponse(url="/dashboard", status_code=303)
        response.set_cookie(key="user_session", value=email, httponly=True)
        return response
    except sqlite3.IntegrityError:
        conn.close()
        return RedirectResponse(url="/?error=Yeh email pehle se registered hai!", status_code=303)

# 3. Login Route
@app.post("/login")
async def login(request: Request, email: str = Form(...), password: str = Form(...)):
    conn = sqlite3.connect('scraper.db')
    c = conn.cursor()
    c.execute("SELECT password FROM users WHERE email = ?", (email,))
    user = c.fetchone()
    conn.close()

    if user and user[0] == password:
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
    
    # YAHAN THEEK KIYA GAYA HAI (NAYA SYNTAX)
    return templates.TemplateResponse(request=request, name="dashboard.html", context={"user": user_email})

# 5. Logout Route
@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("user_session")
    return response

# ==========================================
# SCRAPER API ROUTES (Inhe mat delete karna!)
# ==========================================

@app.post("/scrape_youtube")
async def api_scrape_youtube(urls: str = Form(...)):
    # Yahan aapka youtube scraper call hoga
    return {"results": youtube.scrape_data(urls)}

@app.post("/scrape_tiktok")
async def api_scrape_tiktok(urls: str = Form(...)):
    return {"results": tiktok.scrape_data(urls)}

@app.post("/check_status")
async def api_check_status(urls: str = Form(...)):
    # Agar aapke tiktok.py mein check_status function hai
    return {"results": tiktok.check_status(urls)}