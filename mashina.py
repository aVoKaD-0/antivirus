import subprocess

async def start_vm(name):
    # Команда для клонирования виртуальной машины
    clone_vm_command = f"""
    $sourceVM = "Имя_Исходной_ВМ"
    $newVM = "{name}"
    $vmPath = "C:\\Путь\\К\\ВМ"
    New-VM -Name $newVM -CopyVM $sourceVM -Path $vmPath
    """

    # Выполнение команды клонирования
    subprocess.run(["powershell", "-Command", clone_vm_command], check=True)

    # Команда для запуска .exe файла на виртуальной машине
    run_exe_command = f"""
    $vmName = "{name}"
    $exePath = "C:\\Путь\\К\\Файлу.exe"
    Invoke-Command -VMName $vmName -ScriptBlock {{ Start-Process -FilePath $exePath }}
    """

    # Выполнение команды запуска .exe файла
    subprocess.run(["powershell", "-Command", run_exe_command], check=True)