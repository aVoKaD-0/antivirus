from fastapi import FastAPI, UploadFile, File, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import shutil
import os
import uuid
import json
from datetime import datetime
from typing import Dict, List
from mashina import start_vm
import asyncio

app = FastAPI()

class AnalysisResult(BaseModel):
    analysis_id: str
    result_data: dict

@app.post("/submit-result/")
async def submit_result(result: AnalysisResult):
    try:
        # Обработка и сохранение данных
        os.makedirs("results", exist_ok=True)  # Убедитесь, что папка создается
        with open(f"results/{result.analysis_id}.json", "w") as file:
            json.dump(result.result_data, file)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Настраиваем CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене замените на конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Создаем необходимые директории, если их нет
os.makedirs("uploads", exist_ok=True)
os.makedirs("data", exist_ok=True)  # Новая папка для данных
os.makedirs("results", exist_ok=True)  # Папка для результатов
os.makedirs("static", exist_ok=True)
os.makedirs("templates", exist_ok=True)
os.makedirs("history", exist_ok=True)
os.makedirs("logs", exist_ok=True)

# Монтируем статические файлы
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Хранилище активных анализов по пользователям
active_analyses: Dict[str, Dict[str, List[str]]] = {}

@app.post("/analyze")
async def analyze_file(request: Request, file: UploadFile = File(...)):
    try:
        # Сохранение файла
        client_ip = get_client_ip(request)
        user_upload_folder = os.path.join("uploads", client_ip)
        os.makedirs(user_upload_folder, exist_ok=True)

        file_location = os.path.join(user_upload_folder, file.filename)
        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Генерация идентификатора анализа
        run_id = str(uuid.uuid4())

        # Запуск виртуальной машины асинхронно
        asyncio.create_task(start_vm(run_id, file.filename))

        # Добавляем запись в историю
        history = load_user_history()
        history.append({
            "analysis_id": run_id,
            "filename": file.filename,
            "timestamp": datetime.now().isoformat(),
            "status": "running",
            "file_activity": [],
            "docker_output": ""
        })
        save_user_history(history)

        return {"status": "success", "analysis_id": run_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    # Получаем историю пользователя
    history = load_user_history()

    return templates.TemplateResponse(
        "index.html",
        {"request": request, "history": history}
    )

def load_user_history():
    # Загрузка истории из файла
    history_file = "history/history.json"
    if os.path.exists(history_file):
        with open(history_file, "r") as file:
            return json.load(file)
    return []

@app.get("/history")
async def get_history():
    return {"history": load_user_history()}

@app.get("/results/{analysis_id}")
async def get_results(analysis_id: str):
    try:
        # Получаем историю
        history = load_user_history()
        item = None

        # Ищем текущий анализ
        for entry in history:
            if entry["analysis_id"] == analysis_id:
                item = entry
                break

        if not item:
            return JSONResponse({
                "status": "error",
                "message": "Анализ не найден"
            }, status_code=404)

        return {
            "status": item["status"],
            "file_activity": item.get("file_activity", []),
            "docker_logs": item.get("docker_output", "")
        }

    except Exception as e:
        print(f"Ошибка при получении результатов: {str(e)}")
        return JSONResponse({
            "status": "error",
            "message": str(e)
        }, status_code=404)

@app.get("/analysis/{analysis_id}")
async def get_analysis_page(request: Request, analysis_id: str):
    try:
        history = load_user_history()

        # Проверяем существование анализа
        analysis_exists = any(item["analysis_id"] == analysis_id for item in history)
        if not analysis_exists:
            # Если анализ не найден, перенаправляем на главную
            return RedirectResponse(url="/")

        return templates.TemplateResponse(
            "index.html",
            {"request": request, "history": history}
        )
    except Exception as e:
        print(f"Ошибка при получении страницы анализа: {str(e)}")
        return RedirectResponse(url="/")

@app.delete("/analysis/{analysis_id}")
async def stop_analysis(analysis_id: str):
    try:
        # Удаляем рабочую директорию
        work_dir = os.path.join("data", analysis_id)
        if os.path.exists(work_dir):
            shutil.rmtree(work_dir)

        # Обновляем статус в истории
        history = load_user_history()
        for item in history:
            if item["analysis_id"] == analysis_id:
                item["status"] = "stopped"
                break
        save_user_history(history)

        return {"status": "success", "message": "Анализ остановлен"}
    except Exception as e:
        return JSONResponse({
            "status": "error",
            "message": str(e)
        }, status_code=404)

# @app.get("/containers/")
# async def list_containers():
#     try:
#         # Если Docker не используется, удалите этот эндпоинт
#         containers = client.containers.list(all=True)
#         return [
#             {
#                 "run_id": container.name.replace("monitor-", ""),
#                 "status": container.status,
#                 "id": container.short_id
#             }
#             for container in containers
#             if container.name.startswith("monitor-")
#         ]
#     except Exception as e:
#         return JSONResponse({
#             "status": "error",
#             "message": str(e)
#         }, status_code=500)

def save_user_history(history: list):
    # Определяем путь к файлу истории
    history_dir = "history"
    os.makedirs(history_dir, exist_ok=True)
    history_file = os.path.join(history_dir, "history.json")

    # Сохраняем историю в JSON файл
    with open(history_file, "w") as file:
        json.dump(history, file, indent=4)

# Функция получения IP пользователя
def get_client_ip(request: Request):
    if request.headers.get('X-Forwarded-For'):
        ip = request.headers.get('X-Forwarded-For').split(',')[0]
    else:
        ip = request.client.host
    return ip

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)