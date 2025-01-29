import subprocess
import requests
import json
import os
from shutil import copyfile

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
        source_disk = f"{project_dir}\\Hyper\\dock.vhdx"
        new_vm_folder = f"{project_dir}\\Hyper\\{analysis_id}"
        new_disk = os.path.join(new_vm_folder, "dock.vhdx")

        # Создание новой директории для виртуальной машины
        os.makedirs(new_vm_folder, exist_ok=True)

        # Копирование виртуального диска
        copyfile(source_disk, new_disk)
        print(f"Виртуальный диск скопирован в {new_disk}")

        # Создание новой виртуальной машины
        create_vm_command = f"""
        New-VM -Name "{analysis_id}" -MemoryStartupBytes 2GB -Generation 2
        Add-VMHardDiskDrive -VMName "{analysis_id}" -Path "{new_disk}"
        """
        subprocess.run(["powershell", "-Command", create_vm_command], check=True)
        print(f"Виртуальная машина {analysis_id} создана.")

        # Создание коммутатора
        # create_switch_command = f"""
        # New-VMSwitch -Name "VirtualSwitch1" -SwitchType Internal
        # """
        # subprocess.run(["powershell", "-Command", create_switch_command], check=True)
        # print("Коммутатор VirtualSwitch1 создан.")

        # Подключение сетевого адаптера
        connect_adapter_command = f"""
        $vm = Get-VM -Name "{analysis_id}"
        $adapters = Get-VMNetworkAdapter -VM $vm
        $defaultSwitch = Get-VMSwitch -Id "c08cb7b8-9b3c-408e-8e30-5e16a3aeb444"  # ID Default Switch
        Connect-VMNetworkAdapter -VMName "{analysis_id}" -Name $adapters[0].Name -SwitchName $defaultSwitch.Name
        """
        subprocess.run(["powershell", "-Command", connect_adapter_command], check=True)
        print("Сетевой адаптер подключен к Default Switch.")

        # Проверка, существует ли коммутатор
        switch_exists_command = f"""
        $switch = Get-VMSwitch -Name "VirtualSwitch1" -ErrorAction SilentlyContinue
        if (-not ($switch)) {{
            New-VMSwitch -Name "VirtualSwitch1" -SwitchType External -NetAdapterName "Ethernet"
        }}
        """
        subprocess.run(["powershell", "-Command", switch_exists_command], check=True)
        print("Коммутатор VirtualSwitch1 создан.")

        # Запуск виртуальной машины
        start_vm_command = f"""
        Start-VM -Name "{analysis_id}"
        Invoke-Command -VMName "{analysis_id}" -Credential (Get-Credential) -ScriptBlock {{ Start-Process -FilePath "C:\\Path\\InsideVM\\{exe_filename}" }}
        """
        subprocess.run(["powershell", "-Command", start_vm_command], check=True)
        print(f"Виртуальная машина {analysis_id} запущена и выполняет {exe_filename}.")

        # Настройка автозапуска Procmon
        setup_procmon_command = f"""
        $vmName = "{analysis_id}"
        $procmonPath = "C:\\ProgramData\\Microsoft\\Windows\\Virtual Hard Disks\\Procmon.exe"
        Invoke-Command -VMName $vmName -ScriptBlock {{
            New-Item -Path "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run" -Name "Procmon" -Value "$procmonPath /AcceptEula /Quiet"
        }}
        """
        subprocess.run(["powershell", "-Command", setup_procmon_command], check=True)
        print("Procmon настроен для автозапуска.")

        # Остановка Procmon и сохранение логов
        stop_procmon_command = f"""
        Invoke-Command -VMName "{analysis_id}" -ScriptBlock {{
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