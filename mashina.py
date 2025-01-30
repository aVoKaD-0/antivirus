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

async def start_vm(analysis_id, exe_filename):
    try:
        # Пути
        project_dir = os.getcwd()
        source_vm_name = "dock"  # Имя оригинальной виртуальной машины
        export_path = f"{project_dir}\\Hyper\\ExportedVM"
        new_vm_folder = f"{project_dir}\\Hyper\\{analysis_id}"

        # Импорт виртуальной машины с новым именем
        import_vm_command = f"""
        Import-VM -Path "C:\\Users\\a1010\\Desktop\\dock\\Hyper\\ExportedVM\\docks\\dock\\Virtual Machines\\F885A032-F89E-4494-BFF8-3DFB5457EE77.vmcx" -Copy -GenerateNewId
        Rename-VM -VMName "dock" -NewName "{analysis_id}"
        """
        subprocess.run(["powershell", "-Command", import_vm_command], check=True)
        print(f"Виртуальная машина импортирована как {analysis_id}.")

        # Подключение сетевого адаптера
        connect_adapter_command = f"""
        $vm = Get-VM -Name "{analysis_id}"
        $adapters = Get-VMNetworkAdapter -VM $vm
        $defaultSwitch = Get-VMSwitch -Id "c08cb7b8-9b3c-408e-8e30-5e16a3aeb444"  # ID Default Switch
        Connect-VMNetworkAdapter -VMName "{analysis_id}" -Name $adapters[0].Name -SwitchName $defaultSwitch.Name
        """
        subprocess.run(["powershell", "-Command", connect_adapter_command], check=True)
        print("Сетевой адаптер подключен к Default Switch.")

        # Запуск виртуальной машины и выполнение процесса внутри VM с использованием учетных данных
        try:
            print(f"Запуск виртуальной машины {analysis_id} и выполнение процесса внутри VM с использованием учетных данных")
            start_vm_command = f"""
            $secpasswd = ConvertTo-SecureString "{password}" -AsPlainText -Force
            $credential = New-Object System.Management.Automation.PSCredential ("{username}", $secpasswd)
            Start-VM -Name "{analysis_id}"
            Invoke-Command -VMName "{analysis_id}" -Credential $credential -ScriptBlock {{ Start-Process -FilePath "C:\\Path\\InsideVM\\{exe_filename}" }}
            """
            subprocess.run(["powershell", "-Command", start_vm_command], check=True)
            print(f"Виртуальная машина {analysis_id} запущена и выполняет {exe_filename}.")
        except Exception as e:
            stop_vm_command = f"""
            Stop-VM -Name "{analysis_id}"
            """
            subprocess.run(["powershell", "-Command", stop_vm_command], check=True)
            print(f"Ошибка при запуске виртуальной машины: {str(e)}")
        
        print(f"попытка 2 Запуск виртуальной машины {analysis_id} и выполнение процесса внутри VM с использованием учетных данных")
        start_vm_command = f"""
        $secpasswd = ConvertTo-SecureString "{password}" -AsPlainText -Force
        $credential = New-Object System.Management.Automation.PSCredential ("{username}", $secpasswd)
        Start-VM -Name "{analysis_id}"
        Invoke-Command -VMName "{analysis_id}" -Credential $credential -ScriptBlock {{ Start-Process -FilePath "C:\\Path\\InsideVM\\{exe_filename}" }}
        """
        subprocess.run(["powershell", "-Command", start_vm_command], check=True)
        print(f"Виртуальная машина {analysis_id} запущена и выполняет {exe_filename}.")

        # Настройка автозапуска Procmon
        setup_procmon_command = f"""
        $vmName = "{analysis_id}"
        $procmonPath = "C:\\ProgramData\\Microsoft\\Windows\\Virtual Hard Disks\\Procmon.exe"
        Invoke-Command -VMName $vmName -Credential $credential -ScriptBlock {{
            New-Item -Path "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run" -Name "Procmon" -Value "$procmonPath /AcceptEula /Quiet"
        }}
        """
        subprocess.run(["powershell", "-Command", setup_procmon_command], check=True)
        print("Procmon настроен для автозапуска.")

        # Остановка Procmon и сохранение логов
        stop_procmon_command = f"""
        Invoke-Command -VMName "{analysis_id}" -Credential $credential -ScriptBlock {{
            Stop-Process -Name "Procmon"
        }}
        """
        subprocess.run(["powershell", "-Command", stop_procmon_command], check=True)
        print("Procmon остановлен.")

        # Копирование логов на хост
        logs_destination = os.path.join(new_vm_folder, "logs")
        os.makedirs(logs_destination, exist_ok=True)

        copy_logs_command = f"""
        Copy-VMFile -Name "{analysis_id}" -SourcePath "C:\\ProgramData\\Microsoft\\Windows\\Virtual Hard Disks\\procmon.pml" -DestinationPath "{logs_destination}\\promcon.json" -FileSource Host -CreatePath $true
        """
        subprocess.run(["powershell", "-Command", copy_logs_command], check=True)
        print("Логи Procmon скопированы на хост.")

        # Отправка результатов на сервер
        send_result_to_server(analysis_id, {"status": "success"}, True)
    except Exception as e:
        print(f"Ошибка при запуске виртуальной машины: {str(e)}")
        send_result_to_server(analysis_id, {"status": "error", "message": str(e)}, False)