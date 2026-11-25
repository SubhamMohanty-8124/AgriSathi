
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Optional
from pathlib import Path
from datetime import datetime, timezone
import sqlite3, os, json, uuid, shutil, httpx, base64
from contextlib import contextmanager

BASE = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("DATABASE_PATH", str(BASE.parent / "agrisathi.db")))
MEDIA = BASE.parent / "uploads"
MEDIA.mkdir(exist_ok=True)

app = FastAPI(title="AgriSathi API", version="1.0.0",
              description="Paddy-focused farm decision and risk management platform")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

def now():
    return datetime.now(timezone.utc).isoformat()

@contextmanager
def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS farms(
          id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
          village TEXT DEFAULT '', district TEXT DEFAULT '', state TEXT DEFAULT 'Odisha',
          area_acres REAL DEFAULT 0, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS zones(
          id INTEGER PRIMARY KEY AUTOINCREMENT, farm_id INTEGER NOT NULL REFERENCES farms(id) ON DELETE CASCADE,
          name TEXT NOT NULL, crop TEXT DEFAULT 'Paddy', variety TEXT DEFAULT '',
          area_acres REAL DEFAULT 0, moisture REAL, observation TEXT DEFAULT 'normal',
          notes TEXT DEFAULT '', updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS reports(
          id INTEGER PRIMARY KEY AUTOINCREMENT, zone_id INTEGER REFERENCES zones(id) ON DELETE SET NULL,
          category TEXT NOT NULL, notes TEXT DEFAULT '', photo_path TEXT DEFAULT '',
          audio_path TEXT DEFAULT '', created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS tasks(
          id INTEGER PRIMARY KEY AUTOINCREMENT, zone_id INTEGER REFERENCES zones(id) ON DELETE SET NULL,
          title TEXT NOT NULL, due_date TEXT DEFAULT '', priority TEXT DEFAULT 'normal',
          status TEXT DEFAULT 'pending', notes TEXT DEFAULT '', created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events(
          id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL,
          description TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sensor_readings(
          id INTEGER PRIMARY KEY AUTOINCREMENT, zone_id INTEGER REFERENCES zones(id) ON DELETE CASCADE,
          moisture REAL NOT NULL, temperature REAL, humidity REAL,
          source TEXT NOT NULL DEFAULT 'manual', recorded_at TEXT NOT NULL);
        """)
        if c.execute("SELECT COUNT(*) FROM farms").fetchone()[0] == 0:
            cur = c.execute("INSERT INTO farms(name,village,district,state,area_acres,created_at) VALUES(?,?,?,?,?,?)",
                            ("Demo Paddy Farm", "Sample village", "Ganjam", "Odisha", 3.5, now()))
            fid = cur.lastrowid
            c.execute("INSERT INTO zones(farm_id,name,crop,variety,area_acres,moisture,observation,notes,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                      (fid,"North Paddy Plot","Paddy","Swarna",1.5,38,"normal","Illustrative starter data — replace with field observations.",now()))
            c.execute("INSERT INTO zones(farm_id,name,crop,variety,area_acres,moisture,observation,notes,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                      (fid,"Canal-side Plot","Paddy","MTU 1001",2.0,24,"dry","Illustrative starter data — replace with field observations.",now()))
            c.execute("INSERT INTO events(event_type,description,created_at) VALUES(?,?,?)",
                      ("workspace","Demo workspace created with clearly labelled sample records",now()))
init_db()

class FarmIn(BaseModel):
    name: str
    village: str = ""
    district: str = ""
    state: str = "Odisha"
    area_acres: float = 0
class ZoneIn(BaseModel):
    farm_id: int
    name: str
    crop: str = "Paddy"
    variety: str = ""
    area_acres: float = 0
    moisture: Optional[float] = None
    observation: str = "normal"
    notes: str = ""
class ReportIn(BaseModel):
    zone_id: Optional[int] = None
    category: str
    notes: str = ""
    photo_path: str = ""
    audio_path: str = ""
class TaskIn(BaseModel):
    zone_id: Optional[int] = None
    title: str
    due_date: str = ""
    priority: str = "normal"
    notes: str = ""
class ReadingIn(BaseModel):
    zone_id: int
    moisture: float = Field(ge=0, le=100)
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    source: str = "manual"

def log(c, kind, description):
    c.execute("INSERT INTO events(event_type,description,created_at) VALUES(?,?,?)",(kind,description,now()))

def risk(z):
    m = z["moisture"]
    obs = (z["observation"] or "unknown").lower()
    if obs in ("dry","standing_water","wet") or (m is not None and (m < 30 or m >= 85)):
        level, reason = "HIGH", "Observation or moisture value crossed a demo review threshold."
    elif m is None or obs == "unknown":
        level, reason = "CHECK", "Insufficient field information; record an observation."
    elif m < 45:
        level, reason = "MODERATE", "Moisture is below the demo review threshold of 45%."
    else:
        level, reason = "LOW", "No configured demo threshold was crossed."
    return {"level":level,"reason":reason,"is_demo_rule":True}

@app.get("/")
def home():
    return FileResponse(BASE/"static"/"index.html")

@app.get("/api/health")
def health():
    return {"status":"ok","app":"AgriSathi","database":"sqlite","ai_configured":bool(os.getenv("GEMINI_API_KEY"))}

@app.get("/api/overview")
def overview():
    with db() as c:
        farms=[dict(x) for x in c.execute("SELECT * FROM farms ORDER BY id")]
        zones=[dict(x) for x in c.execute("SELECT * FROM zones ORDER BY id DESC")]
        tasks=[dict(x) for x in c.execute("SELECT * FROM tasks ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END, due_date")]
        reports=[dict(x) for x in c.execute("SELECT r.*,z.name zone_name FROM reports r LEFT JOIN zones z ON z.id=r.zone_id ORDER BY r.id DESC LIMIT 8")]
        events=[dict(x) for x in c.execute("SELECT * FROM events ORDER BY id DESC LIMIT 12")]
    for z in zones: z["risk"]=risk(z)
    return {"farms":farms,"zones":zones,"tasks":tasks,"reports":reports,"events":events,
            "stats":{"farms":len(farms),"zones":len(zones),"high":sum(z["risk"]["level"]=="HIGH" for z in zones),
                     "pending":sum(t["status"]=="pending" for t in tasks)}}

@app.post("/api/farms")
def create_farm(x: FarmIn):
    with db() as c:
        cur=c.execute("INSERT INTO farms(name,village,district,state,area_acres,created_at) VALUES(?,?,?,?,?,?)",
                      (x.name,x.village,x.district,x.state,x.area_acres,now()))
        log(c,"farm",f"Farm created: {x.name}")
        return {"id":cur.lastrowid}

@app.put("/api/farms/{farm_id}")
def update_farm(farm_id:int,x:FarmIn):
    with db() as c:
        if not c.execute("SELECT id FROM farms WHERE id=?",(farm_id,)).fetchone(): raise HTTPException(404,"Farm not found")
        c.execute("UPDATE farms SET name=?,village=?,district=?,state=?,area_acres=? WHERE id=?",
                  (x.name,x.village,x.district,x.state,x.area_acres,farm_id))
        log(c,"farm",f"Farm updated: {x.name}")
    return {"ok":True}

@app.delete("/api/farms/{farm_id}")
def delete_farm(farm_id:int):
    with db() as c:
        row=c.execute("SELECT name FROM farms WHERE id=?",(farm_id,)).fetchone()
        if not row: raise HTTPException(404,"Farm not found")
        c.execute("DELETE FROM farms WHERE id=?",(farm_id,))
        log(c,"farm",f"Farm deleted: {row['name']}")
    return {"ok":True}

@app.post("/api/zones")
def create_zone(x:ZoneIn):
    with db() as c:
        if not c.execute("SELECT id FROM farms WHERE id=?",(x.farm_id,)).fetchone(): raise HTTPException(404,"Farm not found")
        cur=c.execute("""INSERT INTO zones(farm_id,name,crop,variety,area_acres,moisture,observation,notes,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?)""",(x.farm_id,x.name,x.crop,x.variety,x.area_acres,x.moisture,x.observation,x.notes,now()))
        log(c,"zone",f"Field zone created: {x.name}")
        return {"id":cur.lastrowid}

@app.put("/api/zones/{zone_id}")
def update_zone(zone_id:int,x:ZoneIn):
    with db() as c:
        if not c.execute("SELECT id FROM zones WHERE id=?",(zone_id,)).fetchone(): raise HTTPException(404,"Zone not found")
        c.execute("""UPDATE zones SET farm_id=?,name=?,crop=?,variety=?,area_acres=?,moisture=?,observation=?,notes=?,updated_at=?
        WHERE id=?""",(x.farm_id,x.name,x.crop,x.variety,x.area_acres,x.moisture,x.observation,x.notes,now(),zone_id))
        log(c,"zone",f"Field zone updated: {x.name}")
    return {"ok":True}

@app.delete("/api/zones/{zone_id}")
def delete_zone(zone_id:int):
    with db() as c:
        row=c.execute("SELECT name FROM zones WHERE id=?",(zone_id,)).fetchone()
        if not row: raise HTTPException(404,"Zone not found")
        c.execute("DELETE FROM zones WHERE id=?",(zone_id,))
        log(c,"zone",f"Field zone deleted: {row['name']}")
    return {"ok":True}

@app.post("/api/readings")
def add_reading(x:ReadingIn):
    with db() as c:
        z=c.execute("SELECT id,name FROM zones WHERE id=?",(x.zone_id,)).fetchone()
        if not z: raise HTTPException(404,"Zone not found")
        c.execute("INSERT INTO sensor_readings(zone_id,moisture,temperature,humidity,source,recorded_at) VALUES(?,?,?,?,?,?)",
                  (x.zone_id,x.moisture,x.temperature,x.humidity,x.source,now()))
        c.execute("UPDATE zones SET moisture=?,updated_at=? WHERE id=?",(x.moisture,now(),x.zone_id))
        log(c,"reading",f"{x.source.title()} reading recorded for {z['name']}: {x.moisture}% moisture")
    return {"ok":True,"risk":risk({"moisture":x.moisture,"observation":"normal"})}

@app.get("/api/readings/{zone_id}")
def readings(zone_id:int):
    with db() as c:
        return [dict(x) for x in c.execute("SELECT * FROM sensor_readings WHERE zone_id=? ORDER BY id DESC LIMIT 50",(zone_id,))]

@app.post("/api/reports")
def create_report(x:ReportIn):
    with db() as c:
        cur=c.execute("INSERT INTO reports(zone_id,category,notes,photo_path,audio_path,created_at) VALUES(?,?,?,?,?,?)",
                      (x.zone_id,x.category,x.notes,x.photo_path,x.audio_path,now()))
        log(c,"report",f"Field report created: {x.category}")
        return {"id":cur.lastrowid}

@app.post("/api/upload")
async def upload(file:UploadFile=File(...)):
    allowed={"image/jpeg","image/png","image/webp","audio/webm","audio/ogg","audio/mp4","audio/wav","audio/mpeg"}
    if file.content_type not in allowed: raise HTTPException(415,"Unsupported file type")
    data=await file.read()
    if len(data)>12*1024*1024: raise HTTPException(413,"File exceeds 12 MB")
    suffix=Path(file.filename or "upload.bin").suffix[:10] or ".bin"
    name=f"{uuid.uuid4().hex}{suffix}"
    (MEDIA/name).write_bytes(data)
    return {"path":f"/media/{name}"}

@app.get("/media/{name}")
def media(name:str):
    path=(MEDIA/name).resolve()
    if path.parent != MEDIA.resolve() or not path.exists(): raise HTTPException(404,"Media not found")
    return FileResponse(path)

@app.get("/api/reports")
def list_reports():
    with db() as c:
        return [dict(x) for x in c.execute("SELECT r.*,z.name zone_name FROM reports r LEFT JOIN zones z ON z.id=r.zone_id ORDER BY r.id DESC")]

@app.delete("/api/reports/{report_id}")
def delete_report(report_id:int):
    with db() as c:
        row=c.execute("SELECT id FROM reports WHERE id=?",(report_id,)).fetchone()
        if not row: raise HTTPException(404,"Report not found")
        c.execute("DELETE FROM reports WHERE id=?",(report_id,))
        log(c,"report",f"Report {report_id} deleted")
    return {"ok":True}

@app.post("/api/tasks")
def create_task(x:TaskIn):
    with db() as c:
        cur=c.execute("INSERT INTO tasks(zone_id,title,due_date,priority,status,notes,created_at) VALUES(?,?,?,?,?,?,?)",
                      (x.zone_id,x.title,x.due_date,x.priority,"pending",x.notes,now()))
        log(c,"task",f"Task created: {x.title}")
        return {"id":cur.lastrowid}

@app.patch("/api/tasks/{task_id}/toggle")
def toggle_task(task_id:int):
    with db() as c:
        row=c.execute("SELECT status,title FROM tasks WHERE id=?",(task_id,)).fetchone()
        if not row: raise HTTPException(404,"Task not found")
        status="completed" if row["status"]=="pending" else "pending"
        c.execute("UPDATE tasks SET status=? WHERE id=?",(status,task_id))
        log(c,"task",f"Task {status}: {row['title']}")
    return {"status":status}

@app.delete("/api/tasks/{task_id}")
def delete_task(task_id:int):
    with db() as c:
        c.execute("DELETE FROM tasks WHERE id=?",(task_id,))
        log(c,"task",f"Task deleted: {task_id}")
    return {"ok":True}

@app.get("/api/weather")
async def weather(lat:float=19.31,lon:float=84.79):
    url="https://api.open-meteo.com/v1/forecast"
    params={"latitude":lat,"longitude":lon,"current":"temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
            "daily":"precipitation_probability_max,precipitation_sum,temperature_2m_max,temperature_2m_min",
            "timezone":"auto","forecast_days":3}
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            res=await client.get(url,params=params); res.raise_for_status()
        return {"source":"Open-Meteo","fetched_at":now(),"data":res.json()}
    except Exception:
        raise HTTPException(503,"Weather service unavailable. Check connection and try again.")

@app.post("/api/analyse")
async def analyse(file:UploadFile=File(...), crop:str="Paddy", notes:str=""):
    key=os.getenv("GEMINI_API_KEY")
    if not key:
        raise HTTPException(503,"AI analysis is not configured. Add GEMINI_API_KEY on the server. No diagnosis was generated.")
    if file.content_type not in {"image/jpeg","image/png","image/webp"}:
        raise HTTPException(415,"Upload a JPG, PNG or WebP crop image.")
    raw=await file.read()
    if len(raw)>8*1024*1024: raise HTTPException(413,"Image exceeds 8 MB.")
    prompt=("You are an agricultural image triage assistant. Examine this paddy crop image. "
            "Do not claim a definitive diagnosis. Return JSON with: visible_observations, possible_causes "
            "(array with confidence low/medium only), image_quality, recommended_safe_next_steps, "
            "when_to_contact_agriculture_expert, limitations. Do not prescribe pesticides or chemical dosages. "
            "If evidence is insufficient, say so. Crop: "+crop+". Farmer notes: "+notes)
    model=os.getenv("GEMINI_MODEL","gemini-2.5-flash")
    url=f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    payload={"contents":[{"parts":[{"text":prompt},{"inline_data":{"mime_type":file.content_type,"data":base64.b64encode(raw).decode()}}]}],
             "generationConfig":{"temperature":0.2,"responseMimeType":"application/json"}}
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            res=await client.post(url,json=payload); res.raise_for_status()
        body=res.json()
        txt=body["candidates"][0]["content"]["parts"][0]["text"]
        try: result=json.loads(txt)
        except Exception: result={"raw_response":txt}
        return {"provider":"Google Gemini","model":model,"generated_at":now(),
                "disclaimer":"AI-assisted visual triage, not a confirmed diagnosis. Verify with a qualified local agriculture expert.",
                "result":result}
    except httpx.HTTPStatusError as e:
        raise HTTPException(502,f"AI provider returned HTTP {e.response.status_code}. Check model/key configuration.")
    except Exception:
        raise HTTPException(502,"AI analysis failed. No result was saved; retry later.")

@app.get("/api/history")
def history():
    with db() as c:
        return [dict(x) for x in c.execute("SELECT * FROM events ORDER BY id DESC LIMIT 100")]

@app.get("/api/export")
def export_data():
    with db() as c:
        data={}
        for table in ["farms","zones","reports","tasks","events","sensor_readings"]:
            data[table]=[dict(x) for x in c.execute(f"SELECT * FROM {table}")]
    from fastapi.responses import JSONResponse
    return JSONResponse(data,headers={"Content-Disposition":"attachment; filename=agrisathi-export.json"})
