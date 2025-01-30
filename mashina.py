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
        new_vm_folder = f"{project_dir}\\Hyper\\{analysis_id}"

        # Импорт виртуальной машины с новым именем
        print(f"Импорт виртуальной машины с новым именем {analysis_id}")
        import_vm_command = f"""
        Import-VM -Path "C:\\Users\\a1010\\Desktop\\dock\\Hyper\\ExportedVM\\docks\\dock\\Virtual Machines\\F885A032-F89E-4494-BFF8-3DFB5457EE77.vmcx" -Copy -GenerateNewId
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
            # Остановка виртуальной машины
            print(f"Остановка виртуальной машины {analysis_id}")
            stop_vm_command = f"""
            Stop-VM -Name "{analysis_id}"
            """
            subprocess.run(["powershell", "-Command", stop_vm_command], check=True)
            print("stop VM")
            print(f"Ошибка при запуске виртуальной машины: {str(e)}")
            send_result_to_server(analysis_id, {"status": "error", "message": str(e)}, False)

        # Запуск виртуальной машины
        print(f"Запуск виртуальной машины {analysis_id} Номер 2")
        start_vm_command = f"""
        $secpasswd = ConvertTo-SecureString "{password}" -AsPlainText -Force
        $credential = New-Object System.Management.Automation.PSCredential ("{username}", $secpasswd)
        Start-VM -Name "{analysis_id}"
        """
        subprocess.run(["powershell", "-Command", start_vm_command], check=True)
        print(f"Виртуальная машина {analysis_id} запущена.")

        # Ожидание запуска VM
        if not wait_for_vm_running(analysis_id):
            raise Exception(f"Виртуальная машина {analysis_id} не смогла запуститься в течение 300 секунд.")
        
        # Настройка WinRM на виртуальной машине с учётными данными
        print(f"Настройка WinRM на виртуальной машине {analysis_id} {exe_filename}")
        setup_winrm_command = f"""
        $secpasswd = ConvertTo-SecureString "{password}" -AsPlainText -Force
        $credential = New-Object System.Management.Automation.PSCredential ("{username}", $secpasswd)
        Invoke-Command -VMName "{analysis_id}" -Credential $credential -ScriptBlock {{
            winrm quickconfig -quiet -Force
        }}
        """
        subprocess.run(["powershell", "-Command", setup_winrm_command], check=True)
        print("WinRM настроен на виртуальной машине.")

        # Копирование файла в VM
        print(f"Копирование файла в VM {analysis_id} {exe_filename}")
        copy_file_command = f"""
        Copy-VMFile -Name "{analysis_id}" -SourcePath "{project_dir}\\uploads\\{client_ip}\\{exe_filename}" -DestinationPath "C:\\Path\\InsideVM\\{exe_filename}" -CreateFullPath -FileSource Host
        """
        subprocess.run(["powershell", "-Command", copy_file_command], check=True)
        print(f"Файл {exe_filename} успешно скопирован в виртуальную машину {analysis_id}.")

        # # Проверка, работает ли Procmon не нужна
        # print(f"Проверка, работает ли Procmon на виртуальной машине {analysis_id}")
        # check_procmon_command = f"""
        # $secpasswd = ConvertTo-SecureString "{password}" -AsPlainText -Force
        # $credential = New-Object System.Management.Automation.PSCredential ("{username}", $secpasswd)
        # Invoke-Command -VMName "{analysis_id}" -Credential $credential -ScriptBlock {{
        #     $procmon = Get-Process -Name "Procmon" -ErrorAction SilentlyContinue
        #     if ($procmon) {{
        #         Write-Output "Procmon is running."
        #     }} else {{
        #         Write-Output "Procmon is not running."
        #         Start-Process -FilePath "C:\\Users\\docker\\Desktop\\procmon\\Procmon.exe" -ArgumentList "/AcceptEula /Quiet"
        #     }}
        # }}
        # """
        # procmon_status = subprocess.check_output(["powershell", "-Command", check_procmon_command]).decode().strip()
        # print(procmon_status)

        # Настройка и запуск Procmon
        print(f"Настройка и запуск Procmon {analysis_id} {exe_filename}")
        local_procmon_path = "C:\\Users\\a1010\\Desktop\\dock\\tools\\Procmon.exe"
        vm_procmon_path = "C:\\Users\\docker\\Desktop\\procmon\\Procmon.exe"
        
        # Проверка существования файла Procmon на хосте
        if not os.path.exists(local_procmon_path):
            raise FileNotFoundError(f"Procmon.exe не найден по пути {local_procmon_path}")

        setup_and_start_procmon_command = f"""
        $vm_procmon_path = "{vm_procmon_path}"
        $secpasswd = ConvertTo-SecureString "{password}" -AsPlainText -Force
        $credential = New-Object System.Management.Automation.PSCredential ("{username}", $secpasswd)
        Invoke-Command -VMName "{analysis_id}" -Credential $credential -ScriptBlock {{
        if(Test-Path "C:\\Users\\docker\\Desktop\\procmon\\Procmon.exe") {{
            Write-Output "Procmon.exe found"
            Start-Process -FilePath "C:\\Users\\docker\\Desktop\\procmon\\Procmon.exe" -ArgumentList "/AcceptEula /Quiet"
        }} else {{
            Write-Output "Procmon.exe not found"
        }}
        }}
        """
        procmon_output = subprocess.check_output(["powershell", "-Command", setup_and_start_procmon_command]).decode().strip()
        print(procmon_output)

        # Выполнение процесса внутри VM
        print(f"Выполнение процесса внутри VM {analysis_id} {exe_filename}")
        execute_process_command = f"""
        $secpasswd = ConvertTo-SecureString "{password}" -AsPlainText -Force
        $credential = New-Object System.Management.Automation.PSCredential ("{username}", $secpasswd)
        Invoke-Command -VMName "{analysis_id}" -Credential $credential -ScriptBlock {{ Start-Process -FilePath "C:\\Path\\InsideVM\\{exe_filename}" }}
        """
        subprocess.run(["powershell", "-Command", execute_process_command], check=True)
        print(f"Виртуальная машина {analysis_id} выполняет {exe_filename}.")

        # Остановка Procmon и сохранение логов
        print(f"Остановка Procmon на виртуальной машине {analysis_id} {exe_filename}")
        stop_procmon_command = f"""
        $secpasswd = ConvertTo-SecureString "{password}" -AsPlainText -Force
        $credential = New-Object System.Management.Automation.PSCredential ("{username}", $secpasswd)
        Invoke-Command -VMName "{analysis_id}" -Credential $credential -ScriptBlock {{
            Stop-Process -Name "Procmon"
        }}
        """
        subprocess.run(["powershell", "-Command", stop_procmon_command], check=True)
        print("Procmon остановлен.")

        # Копирование логов на хост
        print(f"Копирование логов на хост {analysis_id} {exe_filename}")
        logs_destination = os.path.join(project_dir, "results")
        logs_destination = os.path.join(logs_destination, f"procmon.pml")
        os.makedirs(logs_destination, exist_ok=True)

        copy_logs_command = f"""
        $secpasswd = ConvertTo-SecureString "{password}" -AsPlainText -Force
        $credential = New-Object System.Management.Automation.PSCredential ("{username}", $secpasswd)
        $s = New-PSSession -VMName "{analysis_id}" -Credential $credential
        Copy-Item -Path "C:\\Users\\docker\\Desktop\\logs\\procmon.pml" -Destination "{logs_destination}" -FromSession $s
        """
        subprocess.run(["powershell", "-Command", copy_logs_command], check=True)
        print("Логи Procmon скопированы на хост.")

        # Отправка результатов на сервер
        print(f"Отправка результатов на сервер {analysis_id} {exe_filename}")
        send_result_to_server(analysis_id, {"status": "success"}, True)
    except Exception as e:
        stop_vm_command = f"""
        Stop-VM -Name "{analysis_id}"
        """
        subprocess.run(["powershell", "-Command", stop_vm_command], check=True)
        print("stop VM")
        print(f"Ошибка при запуске виртуальной машины: {str(e)}")
        send_result_to_server(analysis_id, {"status": "error", "message": str(e)}, False)

# Функция ожидания запуска VM
def wait_for_vm_running(vm_name, timeout=300):
    start_time = time.time()
    while time.time() - start_time < timeout:
        get_vm_command = f'Get-VM -Name "{vm_name}" | Select-Object -ExpandProperty State'
        state = subprocess.check_output(["powershell", "-Command", get_vm_command]).decode().strip()
        if state == "Running":
            return True
        time.sleep(5)
    return False