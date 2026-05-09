from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .routers import projects, ingestion, chat

app = FastAPI(title="CreatorJoy API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router, prefix="/projects", tags=["projects"])
app.include_router(ingestion.router, prefix="/projects", tags=["ingestion"])
app.include_router(chat.router, prefix="/projects", tags=["chat"])

app.mount("/downloads", StaticFiles(directory="downloads"), name="downloads")

@app.get("/")
async def root():
    return {"message": "Welcome to CreatorJoy API"}
