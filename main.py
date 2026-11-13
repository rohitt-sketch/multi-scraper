from fastapi import FastAPI, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker
from passlib.context import CryptContext
import uvicorn

from scrapers import tiktok
from scrapers import youtube 

# --- DATABASE SETUP ---
SQLALCHEMY_DATABASE_URL = "sqlite:///./scraper.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    password = Column(String)
    is_admin = Column(Boolean, default=False)
    is_approved = Column(Boolean, default=False)

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- APP SETUP ---
app = FastAPI()
templates = Jinja2Templates(directory="templates")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

@app.on_event("startup")
def startup_event():
    db = SessionLocal()
    if not db.query(User).filter(User.email == "admin@example.com").first():
        admin = User(email="admin@example.com", password=pwd_context.hash("admin123"), is_admin=True, is_approved=True)
        db.add(admin)
        db.commit()
    db.close()

# --- ROUTES ---
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")

@app.post("/register")
def register(email: str = Form(...), password: str = Form(...), db: SessionLocal = Depends(get_db)):
    if db.query(User).filter(User.email == email).first():
        return {"error": "Yeh Email pehle se register hai!"}
    
    new_user = User(email=email, password=pwd_context.hash(password))
    db.add(new_user)
    db.commit()
    return {"message": "Register ho gaya! Ab Admin ke approve karne ka wait karein."}

@app.get("/admin", response_class=HTMLResponse)
def admin_panel(request: Request, db: SessionLocal = Depends(get_db)):
    users = db.query(User).filter(User.is_admin == False).all()
    return templates.TemplateResponse(request=request, name="admin.html", context={"users": users})

@app.get("/admin/approve/{user_id}")
def approve_user(user_id: int, db: SessionLocal = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.is_approved = True
        db.commit()
    return RedirectResponse(url="/admin", status_code=303)

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="dashboard.html")

# --- SCRAPING API ROUTES ---
@app.post("/scrape_tiktok")
async def api_scrape_tiktok(urls: str = Form(...)):
    return {"results": tiktok.scrape_data(urls)}

@app.post("/check_status")
async def api_check_status(urls: str = Form(...)):
    return {"results": tiktok.check_status(urls)}

# YouTube Route
@app.post("/scrape_youtube")
async def api_scrape_youtube(urls: str = Form(...)):
    return {"results": youtube.scrape_data(urls)}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)