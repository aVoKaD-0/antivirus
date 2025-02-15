# antivirus

✅ Веб-интерфейс

✅ Поднятие и настройка VM

✅ Получение файловой активности

✅ возврат результатов пользователю

✅ requirements.txt

***Рассмотрим данный части поподробней.***

Веб-интерфейс включает в себя две страницы, главная страница localhost:8080/ и страница анализа/результата localhost:8080/analysis/analysisId

*Что касается беканд части.*

Сам сервер и клиент написаны на flask.

/analysis/analisysId отвечает за добавление данного анализа в историю, дальнейшего запуска анализа.

/analysis запускает определенный анализ.

/result/analisysId возвращает результаты анализа.

/result/analisysId/chunk Так как результат анализа достаточно объемный, приходится отправлять пользователю его по частям чанк как раз выполняет данную функцию. 

Так же имеются мелочи, по типу удаление анализа, обращение к файлу результатов, получение ip пользователя, их я расписывать не буду, а просто покажу кодом

```python
# Функция получения IP пользователя
def get_client_ip(request: Request):
    if request.headers.get('X-Forwarded-For'):
        ip = request.headers.get('X-Forwarded-For').split(',')[0]
    else:
        ip = request.client.host
    return ip
```

``` python
# Сохраняет словарь результатов анализов в файл results/{analysis_id}/results.json.
def save_user_results(results, analysis_id: str):
    """
    Сохраняет словарь результатов анализов в файл results/{analysis_id}/results.json.
    """
    results_file = f"results/{analysis_id}/results.json"
    with open(results_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, ensure_ascii=False)
```

``` python
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
```

``` python
# Сохраняет историю анализов в файл history/history.json.
def save_user_history(history: list):
    # Определяем путь к файлу истории
    history_dir = "history"
    os.makedirs(history_dir, exist_ok=True)
    history_file = os.path.join(history_dir, "history.json")

    # Сохраняем историю в JSON файл
    with open(history_file, "w") as file:
        json.dump(history, file, indent=4)
```

Сам анализ происходит на VM Hyper-V, Данный способ используется для того, чтобы на наш сервер не проник вирус.

```python
log(f"Импорт виртуальной машины с новым именем {analysis_id}")
        os.path.join(project_dir, "Hyper", analysis_id, "Virtual Hard Disks")
        import_vm_command = f"""
        $vm = Import-VM -Path "{project_dir}\\Hyper\\ExportedVM\\dock\\Virtual Machines\\38EA00DB-AC8B-473C-8A1E-5C973D39DE75.vmcx" -Copy -GenerateNewId -VirtualMachinePath "{project_dir}\\Hyper\\{analysis_id}" -VhdDestinationPath "{project_dir}\\Hyper\\{analysis_id}\\Virtual Machines";
        Rename-VM -VM $vm -NewName "{analysis_id}";
        """
        subprocess.run(["powershell", "-Command", import_vm_command], check=True)
        log(f"Виртуальная машина импортирована как {analysis_id}.")
```
>Импортируем уже готовую машину в новую директорию, это требуется для того, чтобы мы смогли запустить несколько машин.
>Дальше требуется включить интерфейс гостевой службы, копировать файл в машину.
>Файловую активность будем получать с помощью Procmon, она настроена так, чтобы считала только новые активности. Мы не можем отключить проверку определенных активностей, ведь вирусы могут предварятся ими.
>
>По окончанию работы exe файла, требуется отключить Procmon, скопировать файловую активность (PML) на хост.
>Но тип файл PML не подойдет для вывода пользователю, а конвертировать в json на прямую мы не можем. Значит используем CSV.
>И всё, осталось вернуть результат пользователю.
>Но тут возникает вопрос, как нам вернуть результат пользователю, ведь он может весить более 1ГБ и иметь более 1МЛН строк. А для этого мы воспользуемся ленивым чанком, он будет посылать пользователю определенное количество строк. А пользователь уже сам решит, загружать результат на свой компьютер или нет.

*Чтобы запустить мой проект потребуется несколько действий:*
Скопируйте мой проект с помощью команды `git clone URL`. 
Установите все библиотеки с помощью `pip install -r requirements.txt`. 

Установите [Hyper-V](https://learn.microsoft.com/ru-ru/windows-server/virtualization/hyper-v/get-started/Install-Hyper-V?pivots=windows). 
[Скачайте уже готовую виртуальную машину](https://drive.google.com/file/d/1O2mKFO-dGzNK9xcWsChctdy8AfY4qcAr/view?usp=sharing).
Распакуйте .rar  корневую папку проекта.

Запустите файл app.py. 

Всё, на этом мой проект окончен, всем спасибо, всем пока. 
