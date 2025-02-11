from fastapi import FastAPI, UploadFile, File, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse, FileResponse
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
import ijson

app = FastAPI()

class AnalysisResult(BaseModel):
    analysis_id: str
    result_data: dict

@app.post("/submit-result/")
async def submit_result(result: AnalysisResult):
    try:
        # Опционально: обновляем статус анализа в истории,
        # например, если в result_data передан новый статус.
        history = load_user_history()
        for entry in history:
            if entry["analysis_id"] == result.analysis_id:
                entry["status"] = result.result_data.get("status", "completed")
                break
        save_user_history(history)

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

        # Запускаем виртуальную машину асинхронно
        asyncio.create_task(asyncio.to_thread(start_vm, run_id, file.filename, client_ip))

        # Обновляем историю: сохраняем только analysis_id, filename, timestamp и status.
        history = load_user_history()
        history.append({
            "analysis_id": run_id,
            "filename": file.filename,
            "timestamp": datetime.now().isoformat(),
            "status": "running"
        })
        save_user_history(history)

        # Создаем пустую запись в results.json для хранения file_activity и docker_output.
        os.makedirs(os.path.join("results", run_id), exist_ok=True)
        results = load_user_results(run_id)
        results[run_id] = {
            "file_activity": [],
            "docker_output": ""
        }
        save_user_results(results, run_id)

        print(f"Файл загружен и анализ запущен. ID анализа: {run_id}")
        
        return JSONResponse({
            "status": "success",
            "analysis_id": run_id
        })
    except Exception as e:
        print(f"Ошибка при анализе файла: {str(e)}")
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
    # Загрузка истории из файла с использованием кодировки utf-8-sig 
    # для корректного распознавания BOM и избежания ошибок декодирования.
    history_file = "history/history.json"
    if os.path.exists(history_file):
        with open(history_file, "r", encoding="utf-8-sig") as file:
            return json.load(file)
    return []

@app.get("/history")
async def get_history():
    return {"history": load_user_history()}

@app.get("/results/{analysis_id}")
async def get_results(analysis_id: str):
    try:
        history = load_user_history()
        analysis = next((item for item in history if item["analysis_id"] == analysis_id), None)
        if not analysis:
            return JSONResponse(status_code=404, content={"detail": "Анализ не найден"})

        results = load_user_results(analysis_id)
        result_data = {
            "file_activity": results.get("file_activity", []),
            "docker_output": results.get("docker_output", "")
        }
        
        return JSONResponse({
            "status": analysis["status"],
            "file_activity": result_data.get("file_activity", []),
            "docker_output": result_data.get("docker_output", "")
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})

@app.get("/results/{analysis_id}/chunk")
async def get_results_chunk(analysis_id: str, offset: int = 0, limit: int = 50):
    try:
        # Определяем путь к файлу результатов.
        # Предполагается, что результаты хранятся в файле data/{analysis_id}/results.json
        results_file = os.path.join("results", analysis_id, "results.json")
        if not os.path.exists(results_file):
            return JSONResponse(status_code=404, content={"detail": "Результаты не найдены"})

        chunk = []
        total = 0

        # Используем ijson для потокового парсинга ключа "file_activity", который должен быть массивом.
        # Это означает, что структура JSON должна быть примерно такой:
        # {
        #     "file_activity": [ {...}, {...}, ... ],
        #     "docker_output": "..."
        # }
        with open(results_file, "r", encoding="utf-8") as f:
            parser = ijson.items(f, "file_activity.item")
            for item in parser:
                if total >= offset and len(chunk) < limit:
                    chunk.append(item)
                total += 1

        return JSONResponse({
            "chunk": chunk,
            "offset": offset,
            "limit": limit,
            "total": total
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})

@app.get("/analysis/{analysis_id}")
async def get_analysis_page(request: Request, analysis_id: str):
    try:
        history = load_user_history()
        analysis = next((item for item in history if item["analysis_id"] == analysis_id), None)
        if not analysis:
            return RedirectResponse(url="/")

        results = load_user_results(analysis_id)
        result_data = results.get(analysis_id, {"file_activity": [], "docker_output": ""})

        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "analysis_id": analysis_id,
                "status": analysis["status"],
                "file_activity": result_data.get("file_activity", []),
                "docker_output": result_data.get("docker_output", ""),
                "history": history
            }
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

# Сохраняет историю анализов в файл history/history.json.
def save_user_history(history: list):
    # Определяем путь к файлу истории
    history_dir = "history"
    os.makedirs(history_dir, exist_ok=True)
    history_file = os.path.join(history_dir, "history.json")

    # Сохраняем историю в JSON файл
    with open(history_file, "w") as file:
        json.dump(history, file, indent=4)

# Загружает историю анализов из файла history/history.json.
def load_user_results(analysis_id: str):
    """
    Загружает результаты анализов из файла results/{analysis_id}/results.json.
    Если файла нет, возвращается пустой словарь.
    """
    results_file = f"results/{analysis_id}/results.json"
    if os.path.exists(results_file):
        with open(results_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

# Сохраняет словарь результатов анализов в файл results/{analysis_id}/results.json.
def save_user_results(results, analysis_id: str):
    """
    Сохраняет словарь результатов анализов в файл results/{analysis_id}/results.json.
    """
    results_file = f"results/{analysis_id}/results.json"
    with open(results_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, ensure_ascii=False)

# Функция получения IP пользователя
def get_client_ip(request: Request):
    if request.headers.get('X-Forwarded-For'):
        ip = request.headers.get('X-Forwarded-For').split(',')[0]
    else:
        ip = request.client.host
    return ip

@app.get("/results/{analysis_id}/download")
async def download_results(analysis_id: str):
    # Определяем путь к файлу результатов (уже исправленное расположение)
    results_file = os.path.join("results", analysis_id, "results.json")
    if not os.path.exists(results_file):
        return JSONResponse(status_code=404, content={"detail": "Результаты не найдены"})
    return FileResponse(results_file, media_type='application/json', filename="results.json")

@app.get("/download/{analysis_id}", response_class=HTMLResponse)
async def download_page(request: Request, analysis_id: str):
    # URL для скачивания файла
    download_url = f"/results/{analysis_id}/download"
    # Возвращаем простую HTML-страницу, которая через JavaScript перенаправляет пользователя на URL скачивания.
    return f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <title>Начало загрузки</title>
        <script>
            window.onload = function() {{
                window.location.href = "{download_url}";
            }};
        </script>
    </head>
    <body>
        <p>Если загрузка не началась автоматически, нажмите <a href="{download_url}">здесь</a>.</p>
    </body>
    </html>
    """

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
