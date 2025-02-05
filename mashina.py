import subprocess
import requests
import json
import os
from shutil import copyfile
import time

# Получение учетных данных пользователя
username = "docker"
password = "docker"

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

async def start_vm(analysis_id, exe_filename, client_ip):
    try:
        # Пути
        project_dir = os.getcwd()
        new_vm_folder = os.path.join(project_dir, "Hyper", analysis_id)

        # Импорт виртуальной машины с новым именем
        print(f"Импорт виртуальной машины с новым именем {analysis_id}")
        import_vm_command = f"""
        Import-VM -Path "C:\\Users\\a1010\\Desktop\\dock\\Hyper\\ExportedVM\\dock\\Virtual Machines\\B03190D6-F600-4FAF-9EDC-978781C921E3.vmcx" -Copy -GenerateNewId
        Rename-VM -VMName "dock" -NewName "{analysis_id}"
        """
        subprocess.run(["powershell", "-Command", import_vm_command], check=True)
        print(f"Виртуальная машина импортирована как {analysis_id}.")

        # Подключение сетевого адаптера
        print(f"Подключение сетевого адаптера {analysis_id}")
        connect_adapter_command = f"""
        $vm = Get-VM -Name "{analysis_id}"
        $adapters = Get-VMNetworkAdapter -VM $vm
        $defaultSwitch = Get-VMSwitch -Id "c08cb7b8-9b3c-408e-8e30-5e16a3aeb444"  # ID Default Switch
        Connect-VMNetworkAdapter -VMName "{analysis_id}" -Name $adapters[0].Name -SwitchName $defaultSwitch.Name
        """
        subprocess.run(["powershell", "-Command", connect_adapter_command], check=True)
        print("Сетевой адаптер подключен к Default Switch.")

        # Включение Guest Service Interface для VM
        print(f"Включение Guest Service Interface для VM {analysis_id}")
        enable_guest_service_command = f"""
        Enable-VMIntegrationService -VMName "{analysis_id}" -Name "Интерфейс гостевой службы"
        """
        subprocess.run(["powershell", "-Command", enable_guest_service_command], check=True)
        print("Guest Service Interface включен для виртуальной машины.")

        try:
            # Запуск виртуальной машины
            print(f"Запуск виртуальной машины {analysis_id}")
            start_vm_command = f"""
            Start-VM -Name "{analysis_id}"
            """
            subprocess.run(["powershell", "-Command", start_vm_command], check=True)
            print(f"Виртуальная машина {analysis_id} запущена.")
        except Exception as e:
            # Остановка виртуальной машины в случае ошибки
            print(f"Остановка виртуальной машины {analysis_id}")
            stop_vm_command = f"""
            Stop-VM -Name "{analysis_id}"
            """
            subprocess.run(["powershell", "-Command", stop_vm_command], check=True)
            print("VM остановлена")
            print(f"Ошибка при запуске виртуальной машины: {str(e)}")
            send_result_to_server(analysis_id, {"status": "error", "message": str(e)}, False)
            return

        # Ожидание запуска VM
        if not wait_for_vm_running(analysis_id):
            raise Exception(f"Виртуальная машина {analysis_id} не смогла запуститься в течение 300 секунд.")
        
        # # Настройка WinRM на виртуальной машине с учётными данными
        # print(f"Настройка WinRM на виртуальной машине {analysis_id} {exe_filename}")
        # setup_winrm_command = f"""
        # $secpasswd = ConvertTo-SecureString "{password}" -AsPlainText -Force
        # $credential = New-Object System.Management.Automation.PSCredential ("{username}", $secpasswd)
        # Invoke-Command -VMName "{analysis_id}" -Credential $credential -ScriptBlock {{
        #     winrm quickconfig -quiet -Force
                Start-Process powershell.exe -Verb RunAs -ArgumentList "-NoProfile -Command `"winrm quickconfig`""
        # }}
        # """
        # subprocess.run(["powershell", "-Command", setup_winrm_command], check=True)
        # print("WinRM настроен на виртуальной машине.")

        # Настройка и запуск Procmon
        print(f"Настройка и запуск Procmon {analysis_id} {exe_filename}")
        local_procmon_path = "C:\\Users\\a1010\\Desktop\\dock\\tools\\Procmon.exe"
        vm_procmon_path = "C:\\Users\\docker\\Desktop\\procmon\\Procmon.exe"
        log_file_path = "C:\\Users\\docker\\Desktop\\logs\\procmon.pml"
        
        # Проверка существования файла Procmon на хосте
        if not os.path.exists(local_procmon_path):
            raise FileNotFoundError(f"Procmon.exe не найден по пути {local_procmon_path}")

        setup_and_start_procmon_command = f"""
        $secpasswd = ConvertTo-SecureString "{password}" -AsPlainText -Force
        $credential = New-Object System.Management.Automation.PSCredential ("{username}", $secpasswd)
        Invoke-Command -VMName "{analysis_id}" -Credential $credential -ScriptBlock {{
            if (Test-Path "C:\\Users\\docker\\Desktop\\procmon\\Procmon.exe") {{
                Write-Output "Procmon.exe найден по пути vm_procmon_path"
                Start-Process -FilePath "C:\\Users\\docker\\Desktop\\procmon\\Procmon.exe" -Verb RunAs -ArgumentList '/AcceptEula', '/Quiet', '/Minimized', "/Backingfile `\"C:\\Users\\docker\\Desktop\\logs\\procmon.pml`\""
                Write-Output "Procmon запущен с логированием в log_file_path"
            }} else {{
                Write-Output "Procmon.exe не найден по пути vm_procmon_path"
            }}
        }}
        """

        try:
            result = subprocess.run(
                ["powershell", "-Command", setup_and_start_procmon_command],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                print(result.stdout.strip())
            else:
                print(f"Ошибка при выполнении команды Procmon: {result.stderr.strip()}")
                raise subprocess.CalledProcessError(result.returncode, setup_and_start_procmon_command, output=result.stdout, stderr=result.stderr)
        except subprocess.CalledProcessError as e:
            print(f"Ошибка при выполнении команды Procmon: {e}")
            raise

        # Копирование файла в VM
        print(f"Копирование файла в VM {analysis_id} {exe_filename}")
        copy_file_command = f"""
        Copy-VMFile -Name "{analysis_id}" -SourcePath "{project_dir}\\uploads\\{client_ip}\\{exe_filename}" -DestinationPath "C:\\Path\\InsideVM\\{exe_filename}" -CreateFullPath -FileSource Host
        """
        subprocess.run(["powershell", "-Command", copy_file_command], check=True)
        print(f"Файл {exe_filename} успешно скопирован в виртуальную машину {analysis_id}.")

        # Выполнение процесса внутри VM
        print(f"Выполнение процесса внутри VM {analysis_id} {exe_filename}")
        execute_process_command = f"""
        $secpasswd = ConvertTo-SecureString "{password}" -AsPlainText -Force
        $credential = New-Object System.Management.Automation.PSCredential ("{username}", $secpasswd)
        Invoke-Command -VMName "{analysis_id}" -Credential $credential -ScriptBlock {{ Start-Process -FilePath "C:\\Path\\InsideVM\\{exe_filename}" }}
        """
        try:
            subprocess.run(["powershell", "-Command", execute_process_command], check=True)
            print(f"Виртуальная машина {analysis_id} выполняет {exe_filename}.")
        except subprocess.CalledProcessError as e:
            print(f"Ошибка при выполнении процесса внутри VM: {e}")
            raise

        # Добавление задержки для сбора данных Procmon
        print("Ожидание сбора данных Procmon...")
        time.sleep(60)  # Увеличение задержки до 60 секунд

        # Остановка Procmon и сохранение логов
        print(f"Остановка Procmon на виртуальной машине {analysis_id} {exe_filename}")
        stop_procmon_command = f"""
        $secpasswd = ConvertTo-SecureString "{password}" -AsPlainText -Force
        $credential = New-Object System.Management.Automation.PSCredential ("{username}", $secpasswd)
        Invoke-Command -VMName "{analysis_id}" -Credential $credential -ScriptBlock {{
            Stop-Process -Name "Procmon" -Force
        }}
        """
        try:
            subprocess.run(["powershell", "-Command", stop_procmon_command], check=True)
            print("Procmon остановлен.")
        except subprocess.CalledProcessError as e:
            print(f"Ошибка при остановке Procmon: {e}")
            raise

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
                print(result.stdout.strip())
            else:
                print(f"Ошибка при ожидании завершения Procmon: {result.stderr.strip()}")
                raise subprocess.CalledProcessError(result.returncode, wait_process_command, output=result.stdout, stderr=result.stderr)
        except subprocess.CalledProcessError as e:
            print(f"Ошибка при ожидании завершения Procmon: {e}")
            raise

        # Получение информации о задачах BITS (опционально)
        print(f"Получение информации о задачах BITS на виртуальной машине {analysis_id}")
        get_bits_transfer_command = f"""
        $secpasswd = ConvertTo-SecureString "{password}" -AsPlainText -Force
        $credential = New-Object System.Management.Automation.PSCredential ("{username}", $secpasswd)
        Invoke-Command -VMName "{analysis_id}" -Credential $credential -ScriptBlock {{
            Get-BitsTransfer | Format-List
        }}
        """
        try:
            bits_transfer_info = subprocess.check_output(
                ["powershell", "-Command", get_bits_transfer_command],
                stderr=subprocess.STDOUT
            ).decode().strip()
            print(bits_transfer_info)
        except subprocess.CalledProcessError as e:
            print(f"Ошибка при выполнении Get-BitsTransfer: {e.output.strip()}")

        # Копирование логов на хост
        print(f"Копирование логов на хост {analysis_id} {exe_filename}")
        logs_destination = os.path.join(project_dir, "results", analysis_id)
        os.makedirs(logs_destination, exist_ok=True)

        copy_logs_command = f"""
        $secpasswd = ConvertTo-SecureString "{password}" -AsPlainText -Force
        $credential = New-Object System.Management.Automation.PSCredential ("{username}", $secpasswd)
        $s = New-PSSession -VMName "{analysis_id}" -Credential $credential
        Copy-Item -Path "{log_file_path}" -Destination "{logs_destination}\\procmon.pml" -FromSession $s
        """
        try:
            subprocess.run(["powershell", "-Command", copy_logs_command], check=True)
            print("Логи Procmon скопированы на хост.")
        except subprocess.CalledProcessError as e:
            print(f"Ошибка при копировании логов: {e.output.strip()}")

        # Остановка виртуальной машины
        print(f"Остановка виртуальной машины {analysis_id}")
        stop_vm_command = f"""
        Stop-VM -Name "{analysis_id}" -Force
        Remove-VM -Name "{analysis_id}" -Force
        """
        try:
            subprocess.run(["powershell", "-Command", stop_vm_command], check=True)
            print("VM остановлена")
        except subprocess.CalledProcessError as stop_e:
            print(f"Ошибка при остановке VM: {stop_e.output.decode().strip()}")

        # Отправка результатов на сервер
        print(f"Отправка результатов на сервер {analysis_id} {exe_filename}")
        send_result_to_server(analysis_id, {"status": "success"}, True)
    except subprocess.CalledProcessError as e:
        print(f"Ошибка при выполнении команды PowerShell: {e.output.strip()}")
        # Остановка виртуальной машины
        print(f"Остановка виртуальной машины {analysis_id}")
        stop_vm_command = f"""
        Stop-VM -Name "{analysis_id}" -Force
        Remove-VM -Name "{analysis_id}" -Force
        """
        try:
            subprocess.run(["powershell", "-Command", stop_vm_command], check=True)
            print("VM остановлена")
        except subprocess.CalledProcessError as stop_e:
            print(f"Ошибка при остановке VM: {stop_e.output.strip()}")
        print(f"Ошибка при запуске виртуальной машины: {str(e)}")
        send_result_to_server(analysis_id, {"status": "error", "message": str(e)}, False)
    except Exception as e:
        print(f"Произошла ошибка: {str(e)}")
        # Остановка виртуальной машины
        print(f"Остановка виртуальной машины {analysis_id}")
        stop_vm_command = f"""
        Stop-VM -Name "{analysis_id}" -Force
        Remove-VM -Name "{analysis_id}" -Force
        """
        try:
            subprocess.run(["powershell", "-Command", stop_vm_command], check=True)
            print("VM остановлена")
        except subprocess.CalledProcessError as stop_e:
            print(f"Ошибка при остановке VM: {stop_e.output.strip()}")
        send_result_to_server(analysis_id, {"status": "error", "message": str(e)}, False)

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
            print(f"Ошибка при получении состояния VM: {e.output.strip()}")
        time.sleep(5)
    return False
