import subprocess
import requests
import json
import os
from shutil import rmtree
import time
import csv

# Получение учетных данных пользователя
username = "docker"
password = "docker"
project_dir = os.getcwd()
project_dir = project_dir.replace('\\', '\\')

def delete_vm(analysis_id):
    time.sleep(5)
    while True:
        try:
            rmtree(f"{project_dir}\\Hyper\\{analysis_id}")
            break
        except:
            global_log(f"Виртуальная машина {analysis_id} не удалена. Ожидание 5 секунд...")
            time.sleep(5)
    global_log(f"Виртуальная машина {analysis_id} удалена.")

def send_result_to_server(analysis_id, result_data, success: bool):
    url = "http://localhost:8080/submit-result/"

    payload = {
        "analysis_id": analysis_id,
        "result_data": result_data
    }
    headers = {"Content-Type": "application/json"}

    print(payload)

    try:
        response = requests.post(url, data=json.dumps(payload), headers=headers)
        if response.status_code == 200:
            print("Результаты успешно отправлены на сервер")
        else:
            print(f"Ошибка при отправке результатов: {response.status_code}")
    except Exception as e:
        print(f"Ошибка при отправке результатов: {str(e)}")

def global_log(msg):
    print(msg)

def start_vm(analysis_id, exe_filename, client_ip):
    logs = ""
    def log(msg):
        nonlocal logs
        logs += msg + "\n"
        global_log(msg)

    try:
        log(f"Импорт виртуальной машины с новым именем {analysis_id}")
        os.path.join(project_dir, "Hyper", analysis_id, "Virtual Hard Disks")
        import_vm_command = f"""
        $vm = Import-VM -Path "{project_dir}\\Hyper\\ExportedVM\\dock\\Virtual Machines\\38EA00DB-AC8B-473C-8A1E-5C973D39DE75.vmcx" -Copy -GenerateNewId -VirtualMachinePath "{project_dir}\\Hyper\\{analysis_id}" -VhdDestinationPath "{project_dir}\\Hyper\\{analysis_id}\\Virtual Machines";
        Rename-VM -VM $vm -NewName "{analysis_id}";
        """
        subprocess.run(["powershell", "-Command", import_vm_command], check=True)
        log(f"Виртуальная машина импортирована как {analysis_id}.")

        log(f"Виртуальная машина {analysis_id} создана.")

        # log(f"Подключение сетевого адаптера {analysis_id}")
        # connect_adapter_command = f"""
        # $vm = Get-VM -Name "{analysis_id}"
        # $adapters = Get-VMNetworkAdapter -VM $vm
        # # Получаем Default Switch по имени
        # $defaultSwitch = Get-VMSwitch -Name "VirtualSwitch1"
        # Connect-VMNetworkAdapter -VMName "{analysis_id}" -Name $adapters[0].Name -SwitchName $defaultSwitch.Name
        # Write-Output "Сетевой адаптер подключен к Default Switch."
        # """
        # subprocess.run(["powershell", "-Command", connect_adapter_command], check=True)
        # log("Сетевой адаптер подключен к Default Switch.")

        # Включение Guest Service Interface для VM
        log(f"Включение Guest Service Interface для VM {analysis_id}")
        enable_guest_service_command = f"""
        Enable-VMIntegrationService -VMName "{analysis_id}" -Name "Интерфейс гостевой службы"
        """
        subprocess.run(["powershell", "-Command", enable_guest_service_command], check=True)
        log("Guest Service Interface включен для виртуальной машины.")

        try:
            # Запуск виртуальной машины
            log(f"Запуск виртуальной машины {analysis_id}")
            start_vm_command = f"""
            Start-VM -Name "{analysis_id}"
            """
            subprocess.run(["powershell", "-Command", start_vm_command], check=True)
            log(f"Виртуальная машина {analysis_id} запущена.")
        except Exception as e:
            # Остановка виртуальной машины в случае ошибки
            log(f"Остановка виртуальной машины {analysis_id}")
            stop_vm_command = f"""
            Stop-VM -Name "{analysis_id}"
            Remove-VM -Name "{analysis_id}" -Force
            """
            subprocess.run(["powershell", "-Command", stop_vm_command], check=True)
            log("VM остановлена")
            log(f"Ошибка при запуске виртуальной машины: {str(e)}")
            send_result_to_server(analysis_id, {"status": "error", "message": str(e)}, False)
            return

        # Ожидание запуска VM
        if not wait_for_vm_running(analysis_id):
            raise Exception(f"Виртуальная машина {analysis_id} не смогла запуститься в течение 300 секунд.")
        
        # # Настройка частной сети на виртуальной машине
        # log(f"Настройка частной сети на виртуальной машине {analysis_id}")
        # setup_private_network_command = f"""
        # $ErrorActionPreference = "Stop";
        # $secpasswd = ConvertTo-SecureString "{password}" -AsPlainText -Force;
        # $credential = New-Object System.Management.Automation.PSCredential ("{username}", $secpasswd);
        # Invoke-Command -VMName "{analysis_id}" -Credential $credential -ScriptBlock {{
        #     try {{
        #         # Получаем первый активный сетевой адаптер по его InterfaceAlias
        #         $netAdapter = Get-NetAdapter | Where-Object {{$_.Status -eq 'Up'}} | Select-Object -First 1;
        #         if ($netAdapter) {{
        #             $profile = Get-NetConnectionProfile -InterfaceAlias $netAdapter.InterfaceAlias;
        #             if ($profile) {{
        #                 if ($profile.NetworkCategory -ne 'Private') {{
        #                     try {{
        #                         Set-NetConnectionProfile -InterfaceAlias $netAdapter.InterfaceAlias -NetworkCategory Private -ErrorAction Stop;
        #                         Write-Output "Установлен режим подключения Private для адаптера $($netAdapter.Name)";
        #                     }} catch {{
        #                         Write-Output "Ошибка при попытке установить режим Private для адаптера $($netAdapter.Name): $($_.Exception.Message)";
        #                     }}
        #                 }} else {{
        #                     Write-Output "Сетевой адаптер $($netAdapter.Name) уже использует режим Private.";
        #                 }}
        #             }} else {{
        #                 Write-Output "Профиль подключения не найден для адаптера $($netAdapter.Name).";
        #             }}
        #         }} else {{
        #             Write-Output "Активный сетевой адаптер не найден.";
        #         }}
        #     }} catch {{
        #         Write-Output "Произошла непредвиденная ошибка: $($_.Exception.Message)";
        #     }}
        #     exit 0;
        # }};
        # """
        # result = subprocess.run(["powershell", "-Command", setup_private_network_command], capture_output=True, text=True)
        # log("Вывод настройки частной сети:")
        # log(result.stdout)
        # if result.returncode != 0:
        #     log("Ошибка при настройке частной сети:")
        #     log(result.stderr)
        # else:
        #     log("Частная сеть настроена на виртуальной машине.")
        

        # Настройка WinRM на виртуальной машине с учётными данными
        # log(f"Настройка WinRM на виртуальной машине {analysis_id} {exe_filename}")
        # setup_winrm_command = f"""
        # $secpasswd = ConvertTo-SecureString "{password}" -AsPlainText -Force;
        # $credential = New-Object System.Management.Automation.PSCredential ("{username}", $secpasswd);
        # Invoke-Command -VMName "{analysis_id}" -Credential $credential -ScriptBlock {{ 
        #     winrm quickconfig -quiet
        # }}
        # """
        # subprocess.run(["powershell", "-Command", setup_winrm_command], check=True)
        # log("WinRM настроен на виртуальной машине.")

        # Копирование файла в VM
        log(f"Копирование файла в VM {analysis_id} {exe_filename}")
        copy_file_command = f"""
        Copy-VMFile -Name "{analysis_id}" -SourcePath "{project_dir}\\uploads\\{client_ip}\\{exe_filename}" -DestinationPath "C:\\Path\\InsideVM\\{exe_filename}" -CreateFullPath -FileSource Host
        """
        subprocess.run(["powershell", "-Command", copy_file_command], check=True)
        log(f"Файл {exe_filename} успешно скопирован в виртуальную машину {analysis_id}.")

        log(f"Настройка и запуск Procmon {analysis_id} {exe_filename}")
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
                log(result.stdout.strip())
            else:
                log(f"Ошибка при выполнении команды Procmon: {result.stderr.strip()}")
                raise subprocess.CalledProcessError(result.returncode, setup_and_start_procmon_command, output=result.stdout, stderr=result.stderr)
        except subprocess.CalledProcessError as e:
            log(f"Ошибка при выполнении команды Procmon: {e}")
            # Обновляем историю с ошибкой
            update_history_on_error(analysis_id, str(e))
            raise

        log("ожидаем Procmon")
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
                log(result.stdout.strip())
            else:
                log(f"Ошибка при ожидании завершения Procmon: {result.stderr.strip()}")
                raise subprocess.CalledProcessError(result.returncode, wait_process_command, output=result.stdout, stderr=result.stderr)
        except subprocess.CalledProcessError as e:
            log(f"Ошибка при ожидании завершения Procmon: {e}")
            # Обновляем историю с ошибкой
            update_history_on_error(analysis_id, str(e))
            raise

        # Копирование логов на хост с механизмом повторных попыток
        log(f"Копирование логов на хост {analysis_id} {exe_filename}")
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
                log("Логи Procmon скопированы на хост.")
                break  # Если копирование прошло успешно, выходим из цикла
            except subprocess.CalledProcessError as e:
                log(f"Попытка {attempt} копирования завершилась неудачно: {e}. Файл может быть ещё заблокирован.")
                if attempt == max_attempts:
                    log("Превышено число попыток копирования файла. Завершаем процесс.")
                    update_history_on_error(analysis_id, str(e))
                    raise
                else:
                    time.sleep(5)  # Ждем 5 секунд перед следующей попыткой

        # Остановка виртуальной машины
        log(f"Остановка виртуальной машины {analysis_id}")
        stop_vm_command = f"""
        Stop-VM -Name "{analysis_id}" -Force
        Remove-VM -Name "{analysis_id}" -Force
        """
        try:
            subprocess.run(["powershell", "-Command", stop_vm_command], check=True)
            log("VM остановлена")
        except subprocess.CalledProcessError as stop_e:
            log(f"Ошибка при остановке VM: {stop_e.output.decode().strip()}")

        # Отправка результатов на сервер
        log(f"Отправка результатов на сервер {analysis_id} {exe_filename}")
        send_result_to_server(analysis_id, {"status": "success"}, True)

        # После завершения Procmon пробуем экспортировать лог
        results_dir = os.path.join("results", analysis_id)
        pml_file = os.path.join(results_dir, "procmon.pml")
        export_procmon_logs(analysis_id, pml_file)
    except subprocess.CalledProcessError as e:
        log(f"Ошибка при выполнении команды PowerShell: {str(e)}")
        # Остановка виртуальной машины
        log(f"Остановка виртуальной машины {analysis_id}")
        stop_vm_command = f"""
        Stop-VM -Name "{analysis_id}" -Force
        Remove-VM -Name "{analysis_id}" -Force
        """
        try:
            subprocess.run(["powershell", "-Command", stop_vm_command], check=True)
            log("VM остановлена")
        except subprocess.CalledProcessError as stop_e:
            log(f"Ошибка при остановке VM: {stop_e.output.strip()}")
        log(f"Ошибка при запуске виртуальной машины: {str(e)}")
        send_result_to_server(analysis_id, {"status": "error", "message": str(e)}, False)
        update_history_on_error(analysis_id, logs + "\n" + str(e))
        delete_vm(analysis_id)
    except Exception as e:
        log(f"Произошла ошибка: {str(e)}")
        # Остановка виртуальной машины
        log(f"Остановка виртуальной машины {analysis_id}")
        stop_vm_command = f"""
        Stop-VM -Name "{analysis_id}" -Force
        Remove-VM -Name "{analysis_id}" -Force
        """
        try:
            subprocess.run(["powershell", "-Command", stop_vm_command], check=True)
            log("VM остановлена")
        except subprocess.CalledProcessError as stop_e:
            log(f"Ошибка при остановке VM: {stop_e.output.strip()}")
        send_result_to_server(analysis_id, {"status": "error", "message": str(e)}, False)
        update_history_on_error(analysis_id, logs + "\n" + str(e))
        delete_vm(analysis_id)

# Функция ожидания запуска VM
def wait_for_vm_running(vm_name, timeout=300):
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
            global_log(f"Ошибка при получении состояния VM: {e.output.strip()}")
        time.sleep(5)
    return False

def update_history_on_success(analysis_id, docker_output=""):
    history_file = "history/history.json"
    # Определяем папку с результатами и путь к CSV файлу Procmon
    results_dir = os.path.join("results", analysis_id)
    csv_file = os.path.join(results_dir, "procmon.csv")

    # Читаем логи из CSV-файла
    activity = []
    if os.path.exists(csv_file):
         with open(csv_file, "r", encoding="utf-8-sig") as f:
              reader = csv.DictReader(f)
              for row in reader:
                   activity.append(row)

    if not os.path.exists(history_file):
        history = []
    else:
        with open(history_file, "r", encoding="utf-8") as file:
            history = json.load(file)
    
    for entry in history:
        if entry["analysis_id"] == analysis_id:
            entry["status"] = "completed"
            entry["file_activity"] = activity
            entry["docker_output"] = docker_output
            break
    
    with open(history_file, "w", encoding="utf-8") as file:
        json.dump(history, file, indent=4, ensure_ascii=False)

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

def parse_bits_transfer(bits_output):
    # Парсинг вывода Get-BitsTransfer и возвращение списка файловой активности
    # Здесь можно реализовать разбор строки или использовать другие методы.
    # В данном примере просто возвращаем список строк
    return bits_output.split('\n') if bits_output else []

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
        global_log("Экспортируем логи Procmon в CSV...")
        subprocess.run(["powershell", "-Command", export_command], check=True)

        time.sleep(20)

        global_log("Конвертируем CSV в JSON...")
        activity = []
        with open(csv_file, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("Process Name") != "Procmon64.exe" and row.get("Process Name") != "Procmon.exe":
                    activity.append(row)

        global_log("Сохраняем результаты в файл...")

        results_data = load_results(analysis_id)

        results_data["file_activity"] = activity

        save_results(results_data, analysis_id)
        global_log(f"Результаты сохранены в results_data")
        delete_vm(analysis_id)
    except Exception as e:
        global_log(f"Ошибка при экспорте логов Procmon: {e}")
        delete_vm(analysis_id)


def load_results(analysis_id: str):
    results_file = os.path.join("results", f"{analysis_id}", "result.json")
    if os.path.exists(results_file):
        with open(results_file, "r", encoding="utf-8") as file:
            return json.load(file)
    # Если файла нет, возвращаем объект с нужной структурой по умолчанию.
    return {"file_activity": [], "docker_output": ""}

def save_results(results, analysis_id: str):
    with open(f"results/{analysis_id}/results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, ensure_ascii=False)


def load_user_history():
    history_file = "history/history.json"
    if os.path.exists(history_file):
        with open(history_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_user_history(history):
    with open("history/history.json", "w", encoding="utf-8") as f:
        json.dump(history, f, indent=4, ensure_ascii=False)
