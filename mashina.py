import subprocess
import requests
import json
import os
from shutil import rmtree
import time
import csv
from filelock import FileLock

# Получение учетных данных пользователя
username = "docker"
password = "docker"
project_dir = os.getcwd()
project_dir = project_dir.replace('\\', '\\')

def start_vm(analysis_id, exe_filename, client_ip):
    logs = ""
    def log(msg, analysis_id):
        nonlocal logs
        logs += msg + "\n"
        global_log(msg, analysis_id)

    try:
        log(f"Импорт виртуальной машины с новым именем {analysis_id}", analysis_id)
        os.path.join(project_dir, "Hyper", analysis_id, "Virtual Hard Disks")
        import_vm_command = f"""
        $vm = Import-VM -Path "{project_dir}\\Hyper\\ExportedVM\\dock\\Virtual Machines\\38EA00DB-AC8B-473C-8A1E-5C973D39DE75.vmcx" -Copy -GenerateNewId -VirtualMachinePath "{project_dir}\\Hyper\\{analysis_id}" -VhdDestinationPath "{project_dir}\\Hyper\\{analysis_id}\\Virtual Machines";
        Rename-VM -VM $vm -NewName "{analysis_id}";
        """
        subprocess.run(["powershell", "-Command", import_vm_command], check=True)
        log(f"Виртуальная машина импортирована как {analysis_id}.", analysis_id)

        log(f"Виртуальная машина {analysis_id} создана.", analysis_id)

        # Включение Guest Service Interface для VM
        log(f"Включение Guest Service Interface для VM {analysis_id}", analysis_id)
        enable_guest_service_command = f"""
        Enable-VMIntegrationService -VMName "{analysis_id}" -Name "Интерфейс гостевой службы"
        """
        subprocess.run(["powershell", "-Command", enable_guest_service_command], check=True)
        log("Guest Service Interface включен для виртуальной машины.", analysis_id)

        try:
            # Запуск виртуальной машины
            log(f"Запуск виртуальной машины {analysis_id}", analysis_id)
            start_vm_command = f"""
            Start-VM -Name "{analysis_id}"
            """
            subprocess.run(["powershell", "-Command", start_vm_command], check=True)
            log(f"Виртуальная машина {analysis_id} запущена.", analysis_id)
        except Exception as e:
            # Остановка виртуальной машины в случае ошибки
            log(f"Остановка виртуальной машины {analysis_id}", analysis_id)
            stop_vm_command = f"""
            Stop-VM -Name "{analysis_id}"
            Remove-VM -Name "{analysis_id}" -Force
            """
            subprocess.run(["powershell", "-Command", stop_vm_command], check=True)
            log("VM остановлена", analysis_id)
            log(f"Ошибка при запуске виртуальной машины: {str(e)}", analysis_id)
            send_result_to_server(analysis_id, {"status": "error", "message": str(e)}, False)
            return

        # Ожидание запуска VM
        if not wait_for_vm_running(analysis_id, analysis_id):
            raise Exception(f"Виртуальная машина {analysis_id} не смогла запуститься в течение 300 секунд.", analysis_id)
        
        # Копирование файла в VM
        log(f"Копирование файла в VM {analysis_id} {exe_filename}", analysis_id)
        copy_file_command = f"""
        Copy-VMFile -Name "{analysis_id}" -SourcePath "{project_dir}\\uploads\\{client_ip}\\{exe_filename}" -DestinationPath "C:\\Path\\InsideVM\\{exe_filename}" -CreateFullPath -FileSource Host
        """
        subprocess.run(["powershell", "-Command", copy_file_command], check=True)
        log(f"Файл {exe_filename} успешно скопирован в виртуальную машину {analysis_id}.", analysis_id)

        log(f"Настройка и запуск Procmon {analysis_id} {exe_filename}", analysis_id)
        local_procmon_path = f"{project_dir}\\tools\\Procmon.exe"
        
        # Проверка существования файла Procmon на хосте
        if not os.path.exists(local_procmon_path):
            raise FileNotFoundError(f"Procmon.exe не найден по пути {local_procmon_path}")

        setup_and_start_procmon_command = f"""
        $secpasswd = ConvertTo-SecureString "{password}" -AsPlainText -Force;
        $credential = New-Object System.Management.Automation.PSCredential ("{username}", $secpasswd);
        $session = New-PSSession -VMName "{analysis_id}" -Credential $credential;
        Invoke-Command -Session $session -ScriptBlock {{
            $procmonPath = "C:\\Users\\docker\\Desktop\\procmon\\Procmon.exe";
            $logFile = "C:\\Users\\docker\\Desktop\\logs\\procmon.pml";
            if (Test-Path $procmonPath) {{
                Write-Output "Procmon.exe найден.";
                # Создаём каталог для логов, если его нет
                $logDir = Split-Path $logFile;
                if (!(Test-Path $logDir)) {{
                    New-Item -ItemType Directory -Path $logDir -Force;
                }}
                Start-Process -FilePath $procmonPath -ArgumentList '/AcceptEula', '/Quiet', '/Minimized' -PassThru;
                Write-Output "Procmon запущен с логированием в $logFile";
            }} else {{
                Write-Output "Procmon.exe не найден.";
            }}
            Write-Output "Ожидание 5 секунд..."
            Start-Sleep -Seconds 5
            Write-Output "Запуск {exe_filename}..."
            Start-Process -FilePath "C:\\Path\\InsideVM\\{exe_filename}"
            Write-Output "Ожидание 70 секунд..."
            Start-Sleep -Seconds 70
            Write-Output "Остановка Procmon..."
            C:\\Users\\docker\\Desktop\\procmon\\Procmon.exe /Terminate
            Write-Output "Procmon остановлен."
        }};
        Remove-PSSession $session;
        """

        try:
            result = subprocess.run(
                ["powershell", "-Command", setup_and_start_procmon_command],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                log(result.stdout.strip(), analysis_id)
            else:
                log(f"Ошибка при выполнении команды Procmon: {result.stderr.strip()}", analysis_id)
                raise subprocess.CalledProcessError(result.returncode, setup_and_start_procmon_command, output=result.stdout, stderr=result.stderr)
        except subprocess.CalledProcessError as e:
            log(f"Ошибка при выполнении команды Procmon: {e}", analysis_id)
            # Обновляем историю с ошибкой
            update_history_on_error(analysis_id, str(e))
            raise

        log("ожидаем Procmon", analysis_id)
        time.sleep(10)

        # Проверка завершения Procmon
        wait_process_command = f"""
        $proc = Get-Process -Name "procmon" -ErrorAction SilentlyContinue
        while ($proc) {{
            Start-Sleep -Seconds 1
            $proc = Get-Process -Name "procmon" -ErrorAction SilentlyContinue
        }}
        Write-Output "Procmon завершен."
        """
        try:
            result = subprocess.run(
                ["powershell", "-Command", wait_process_command],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                log(result.stdout.strip(), analysis_id)
            else:
                log(f"Ошибка при ожидании завершения Procmon: {result.stderr.strip()}", analysis_id)
                raise subprocess.CalledProcessError(result.returncode, wait_process_command, output=result.stdout, stderr=result.stderr)
        except subprocess.CalledProcessError as e:
            log(f"Ошибка при ожидании завершения Procmon: {e}", analysis_id)
            # Обновляем историю с ошибкой
            update_history_on_error(analysis_id, str(e))
            raise

        # Копирование логов на хост с механизмом повторных попыток
        log(f"Копирование логов на хост {analysis_id} {exe_filename}", analysis_id)
        logs_destination = os.path.join(project_dir, "results", analysis_id, "procmon.pml")
        os.makedirs(os.path.dirname(logs_destination), exist_ok=True)

        copy_logs_command = f"""
        $secpasswd = ConvertTo-SecureString "{password}" -AsPlainText -Force;
        $credential = New-Object System.Management.Automation.PSCredential ("{username}", $secpasswd);
        $log_file_path = "C:\\Users\\docker\\Desktop\\logs\\procmon.pml";
        $logs_destination = "{logs_destination}";
        $s = New-PSSession -VMName "{analysis_id}" -Credential $credential;
        Copy-Item -Path "$log_file_path" -Destination "$logs_destination" -FromSession $s
        """

        max_attempts = 5
        for attempt in range(1, max_attempts + 1):
            try:
                subprocess.run(["powershell", "-Command", copy_logs_command], check=True, capture_output=True, text=True)
                log("Логи Procmon скопированы на хост.", analysis_id)
                break  # Если копирование прошло успешно, выходим из цикла
            except subprocess.CalledProcessError as e:
                log(f"Попытка {attempt} копирования завершилась неудачно: {e}. Файл может быть ещё заблокирован.", analysis_id)
                if attempt == max_attempts:
                    log("Превышено число попыток копирования файла. Завершаем процесс.", analysis_id)
                    update_history_on_error(analysis_id, str(e))
                    raise
                else:
                    time.sleep(5)  # Ждем 5 секунд перед следующей попыткой

        # Остановка виртуальной машины
        log(f"Остановка виртуальной машины {analysis_id}", analysis_id)
        stop_vm_command = f"""
        Stop-VM -Name "{analysis_id}" -Force
        Remove-VM -Name "{analysis_id}" -Force
        """
        try:
            subprocess.run(["powershell", "-Command", stop_vm_command], check=True)
            log("VM остановлена", analysis_id)
        except subprocess.CalledProcessError as stop_e:
            log(f"Ошибка при остановке VM: {stop_e.output.decode().strip()}", analysis_id)

        # После завершения Procmon пробуем экспортировать лог
        results_dir = os.path.join("results", analysis_id)
        pml_file = os.path.join(results_dir, "procmon.pml")
        export_procmon_logs(analysis_id, pml_file)
    except subprocess.CalledProcessError as e:
        log(f"Ошибка при выполнении команды PowerShell: {str(e)}", analysis_id)
        # Остановка виртуальной машины
        log(f"Остановка виртуальной машины {analysis_id}", analysis_id)
        stop_vm_command = f"""
        Stop-VM -Name "{analysis_id}" -Force
        Remove-VM -Name "{analysis_id}" -Force
        """
        try:
            subprocess.run(["powershell", "-Command", stop_vm_command], check=True)
            log("VM остановлена", analysis_id)
        except subprocess.CalledProcessError as stop_e:
            log(f"Ошибка при остановке VM: {stop_e.output.strip()}", analysis_id)
        log(f"Ошибка при запуске виртуальной машины: {str(e)}", analysis_id)
        send_result_to_server(analysis_id, {"status": "error", "message": str(e)}, False)
        update_history_on_error(analysis_id, logs + "\n" + str(e))
        delete_vm(analysis_id)
    except Exception as e:
        log(f"Произошла ошибка: {str(e)}", analysis_id)
        # Остановка виртуальной машины
        log(f"Остановка виртуальной машины {analysis_id}", analysis_id)
        stop_vm_command = f"""
        Stop-VM -Name "{analysis_id}" -Force
        Remove-VM -Name "{analysis_id}" -Force
        """
        try:
            subprocess.run(["powershell", "-Command", stop_vm_command], check=True)
            log("VM остановлена", analysis_id)
        except subprocess.CalledProcessError as stop_e:
            log(f"Ошибка при остановке VM: {stop_e.output.strip()}", analysis_id)
        send_result_to_server(analysis_id, {"status": "error", "message": str(e)}, False)
        update_history_on_error(analysis_id, logs + "\n" + str(e))
        delete_vm(analysis_id)

# Функция ожидания запуска VM
def wait_for_vm_running(vm_name, analysis_id, timeout=300):
    start_time = time.time()
    while time.time() - start_time < timeout:
        get_vm_command = f'Get-VM -Name "{vm_name}" | Select-Object -ExpandProperty State'
        try:
            state = subprocess.check_output(
                ["powershell", "-Command", get_vm_command],
                stderr=subprocess.STDOUT
            ).decode().strip()
            if state == "Running":
                return True
        except subprocess.CalledProcessError as e:
            global_log(f"Ошибка при получении состояния VM: {e.output.strip()}", analysis_id)
        time.sleep(5)
    return False

def export_procmon_logs(analysis_id, pml_file_path):
    """
    Экспортирует лог Procmon из формата PML в CSV, затем конвертирует CSV в JSON.
    Обновляет запись в истории с файловой активностью.
    """
    results_dir = os.path.join("results", analysis_id)
    csv_file = os.path.join(results_dir, "procmon.csv")

    # Команда для экспорта логов из PML в CSV с использованием Procmon.exe.
    # Убедитесь, что Procmon.exe доступен (или задайте полный путь к нему).
    export_command = f'{project_dir}\\tools\\Procmon.exe /OpenLog "{pml_file_path}" /SaveAs "{csv_file}" /Quiet'
    try:
        global_log("Экспортируем логи Procmon в CSV...", analysis_id)
        subprocess.run(["powershell", "-Command", export_command], check=True)

        time.sleep(30)

        global_log("Конвертируем CSV в JSON...", analysis_id)
        activity = []
        with open(csv_file, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("Process Name") != "Procmon64.exe" and row.get("Process Name") != "Procmon.exe":
                    activity.append(row)

        global_log("Сохраняем результаты в файл...", analysis_id)

        results_data = load_results(analysis_id)

        results_data["file_activity"] = activity

        save_results(results_data, analysis_id)
        global_log(f"Результаты сохранены в results_data", analysis_id)
        
        os.remove(f"{project_dir}\\results\\{analysis_id}\\procmon.csv")
        os.remove(f"{project_dir}\\results\\{analysis_id}\\procmon.pml")
        # Отправка результатов на сервер
        send_result_to_server(analysis_id, {"status": "completed"}, True)
        delete_vm(analysis_id)
    except Exception as e:
        global_log(f"Ошибка при экспорте логов Procmon: {e}", analysis_id)
        send_result_to_server(analysis_id, {"status": "error", "message": str(e)}, False)
        delete_vm(analysis_id)

def update_history_on_error(analysis_id, error_message):
    history_file = "history/history.json"
    if not os.path.exists(history_file):
        history = []
    else:
        with open(history_file, "r") as file:
            history = json.load(file)
    
    for entry in history:
        if entry["analysis_id"] == analysis_id:
            entry["status"] = "error"
            entry["file_activity"] = []
            entry["docker_output"] = error_message
            break
    
    with open(history_file, "w") as file:
        json.dump(history, file, indent=4)

def load_results(analysis_id: str):
    results_file = os.path.join("results", analysis_id, "results.json")
    lock = FileLock(results_file + ".lock")
    with lock:
        if os.path.exists(results_file):
            with open(results_file, "r", encoding="utf-8") as file:
                return json.load(file)
        # Если файла нет, возвращаем объект с нужной структурой по умолчанию.
        return {"file_activity": [], "docker_output": ""}

def save_results(results, analysis_id: str):
    results_file = os.path.join("results", analysis_id, "results.json")
    lock = FileLock(results_file + ".lock")
    with lock:
        with open(results_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=4, ensure_ascii=False)

def delete_vm(analysis_id):
    time.sleep(5)
    while True:
        try:
            rmtree(f"{project_dir}\\Hyper\\{analysis_id}")
            break
        except:
            global_log(f"Виртуальная машина {analysis_id} не удалена. Ожидание 5 секунд...", analysis_id)
            time.sleep(5)
    global_log(f"Виртуальная машина {analysis_id} удалена.", analysis_id)

def send_result_to_server(analysis_id, result_data, success: bool):
    url = "http://localhost:8080/submit-result/"
    
    payload = {
        "analysis_id": analysis_id,
        "result_data": result_data
    }
    headers = {"Content-Type": "application/json"}
    
    try:
        response = requests.post(url, data=json.dumps(payload), headers=headers)
        if response.status_code == 200:
            global_log(f"Результаты отправлены на сервер", analysis_id)
            # Отправляем уведомление через SSE с информацией для редиректа
            try:
                from app import subscribers, app_loop
                import asyncio
                update_msg = {"analysis_id": analysis_id, "status": result_data.get("status", "completed")}
                # Если статус завершён, добавляем поле redirect с URL для обновления страницы
                if result_data.get("status", "completed") == "completed":
                    update_msg["redirect"] = f"/analysis/{analysis_id}"
                # Для каждого подписчика отсылаем событие через существующий event loop
                for q in subscribers:
                    asyncio.run_coroutine_threadsafe(q.put(update_msg), app_loop)
            except Exception as se:
                global_log(f"Ошибка при отправке SSE уведомления: {str(se)}", analysis_id)
        else:
            global_log(f"Ошибка при отправке результатов: {response.status_code}", analysis_id)
    except Exception as e:
        global_log(f"Ошибка при отправке результатов: {str(e)}", analysis_id)

def global_log(msg, analysis_id):
    results_data = load_results(analysis_id)
    results_data["docker_output"] += msg + ";   "
    save_results(results_data, analysis_id)
