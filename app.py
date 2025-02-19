from fastapi import FastAPI, UploadFile, File, Request, HTTPException, WebSocket, WebSocketDisconnect
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
import re
from contextlib import asynccontextmanager
import websocket_manager
import logging

file_log = os.path.join("data", "log.log")
logging.basicConfig(level=logging.DEBUG, filename=file_log)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global websocket_manager
    websocket_manager.app_loop = asyncio.get_running_loop()
    yield

app = FastAPI(lifespan=lifespan)

class AnalysisResult(BaseModel):
    analysis_id: str
    result_data: dict

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

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    global_log(f"connect {request.client.host}")
    # Получаем историю пользователя
    history = load_user_history()

    return templates.TemplateResponse(
        "index.html",
        {"request": request, "history": history}
    )

@app.get("/analysis/{analysis_id}")
async def get_analysis_page(request: Request, analysis_id: str):
    try:
        global_log(f"get_analysis_page {analysis_id}, {request.client.host}")
        history = load_user_history()
        analysis = next((item for item in history if item["analysis_id"] == analysis_id), None)
        if not analysis:
            return RedirectResponse(url="/")
        
        if websocket_manager.app_loop is None:
            websocket_manager.app_loop = asyncio.get_running_loop()
        
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "analysis_id": analysis_id,
                "status": analysis["status"],
                "file_activity": [],
                "docker_output": "",
                "history": history
            }
        )
    except Exception as e:
        return RedirectResponse(url="/")

@app.delete("/analysis/{analysis_id}")
async def stop_analysis(analysis_id: str):
    try:
        # Удаляем рабочую директорию
        global_log(f"stop_analysis {analysis_id}")
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

        global_log(f"analyze_file {run_id}, {file.filename}, {client_ip}")
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
        save_user_results(results, run_id)

        global_log(f"Файл загружен и анализ запущен. ID анализа: {run_id}, {request.client.host}")
        
        return JSONResponse({
            "status": "success",
            "analysis_id": run_id
        })
    except Exception as e:
        global_log(f"Ошибка при анализе файла: {str(e)}", run_id, request.client.host)
        raise HTTPException(status_code=500, detail=str(e))

def load_user_history():
    # Загрузка истории из файла с использованием кодировки utf-8-sig 
    # для корректного распознавания BOM и избежания ошибок декодирования.
    history_file = "history/history.json"
    if os.path.exists(history_file):
        with open(history_file, "r", encoding="utf-8-sig") as file:
            return json.load(file)
    return []

@app.get("/results/{analysis_id}")
async def get_results(analysis_id: str):
    try:
        result_data = get_result_data(analysis_id)
        return JSONResponse(result_data)
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})

@app.get("/results/{analysis_id}/chunk")
async def get_results_chunk(analysis_id: str, offset: int = 0, limit: int = 50):
    global_log(f"get_results_chunk {analysis_id}")
    try:
        # Определяем путь к файлу результатов.
        # Предполагается, что результаты хранятся в файле data/{analysis_id}/results.json
        results_file = os.path.join("results", analysis_id, "results.json")
        if not os.path.exists(results_file):
            return JSONResponse(status_code=404, content={"detail": "Результаты не найдены"})

        chunk = []
        total = 0

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
    
def get_result_data(analysis_id: str) -> dict:
    """
    Формирует данные результатов, не считывая весь файл сразу.
    Использует потоковый парсер для извлечения первых 500000 элементов массива file_activity.
    Также возвращается общее количество элементов (поле total) и docker_output.
    """
    results_file = os.path.join("results", analysis_id, "results.json")

    preview = []
    total = 0
    # Читаем только массив file_activity через ijson, чтобы избежать загрузки полного файла в память
    with open(results_file, "r", encoding="utf-8") as f:
         parser = ijson.items(f, "file_activity.item")
         for item in parser:
             if total < 100:
                 preview.append(item)
             total += 1

    docker_output = ""
    # Если docker_output находится в конце файла, читаем последние 100 КБ
    with open(results_file, "rb") as f:
         f.seek(0, os.SEEK_END)
         file_size = f.tell()
         read_size = 1000 * 1024  # 100 КБ
         start_pos = max(file_size - read_size, 0)
         f.seek(start_pos)
         tail = f.read().decode("utf-8", errors="replace")
         m = re.search(r'"docker_output"\s*:\s*"([^"]*)"', tail)
         if m:
             docker_output = m.group(1)

    result = {
         "file_activity": preview,
         "docker_output": docker_output,
         "total": total
    }
    return result
    
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
    return {"file_activity": [], "docker_output": ""}

# Сохраняет словарь результатов анализов в файл results/{analysis_id}/results.json.
def save_user_results(results, analysis_id: str):
    """
    Сохраняет словарь результатов анализов в файл results/{analysis_id}/results.json.
    """
    results_file = f"results/{analysis_id}/results.json"
    with open(results_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, ensure_ascii=False)

@app.get("/history")
async def get_history():
    return {"history": load_user_history()}

# Сохраняет историю анализов в файл history/history.json.
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

@app.get("/results/{analysis_id}/download")
async def download_results(analysis_id: str):
    # Определяем путь к файлу результатов (уже исправленное расположение)
    results_file = os.path.join("results", analysis_id, "results.json")
    global_log(f"download_results {analysis_id}, {results_file}")
    if not os.path.exists(results_file):
        return JSONResponse(status_code=404, content={"detail": "Результаты не найдены"})
    return FileResponse(results_file, media_type='application/json', filename="results.json")

@app.get("/download/{analysis_id}", response_class=HTMLResponse)
async def download_page(request: Request, analysis_id: str):
    global_log(f"download_page {analysis_id}, {request.client.host}")
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

@app.post("/submit-result/")
async def submit_result(result: AnalysisResult):
    try:
        global_log(f"submit_result {result.analysis_id}, {result.result_data}")
        history = load_user_history()
        for entry in history:
            if entry["analysis_id"] == result.analysis_id:
                entry["status"] = result.result_data.get("status", "completed")
                entry["docker_output"] = result.result_data.get("message", entry.get("docker_output", ""))
                break
        save_user_history(history)
        return {"status": "completed"}
    except Exception as e:
        global_log(f"submit_result error {result.analysis_id} {str(e)}, {result.result_data}")
        raise HTTPException(status_code=500, detail=str(e))

# Эндпоинт для WebSocket
@app.websocket("/ws/{analysis_id}")
async def websocket_endpoint(websocket: WebSocket, analysis_id: str):
    await websocket_manager.manager.connect(analysis_id, websocket)
    try:
        # Оставляем соединение открытым, можем ожидать сообщения от клиента (если потребуется)
        global_log(f"connect websocket {analysis_id}, {websocket.client.host}")
        while True:
            _ = await websocket.receive_text()
    except WebSocketDisconnect:
        global_log(f"disconnect websocket {analysis_id}, {websocket.client.host}")
        websocket_manager.manager.disconnect(analysis_id, websocket)

def global_log(message):
    logging.debug(message)

if __name__ == "__main__":
    import asyncio
    if websocket_manager.app_loop is None:
        websocket_manager.app_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(websocket_manager.app_loop)
        global_log("app_loop установлен внутри __main__")
    else:
        global_log("app_loop уже установлен")
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
