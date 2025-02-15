console.log("script.js loaded");

document.addEventListener('DOMContentLoaded', function() {
    // Выведем значение глобальной переменной analysisId для отладки
    console.log("Global analysisId:", (typeof analysisId !== "undefined") ? analysisId : "undefined");

    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('fileInput');
    const progressBar = document.getElementById('progressBar');
    const progress = document.getElementById('progress');
    const resultsSection = document.getElementById('resultsSection');
    const analysisStatus = document.getElementById('analysisStatus');
    const fileActivityContent = document.getElementById('fileActivityContent');
    const dockerOutputContent = document.getElementById('dockerOutputContent');
    const statusSpinner = document.getElementById('statusSpinner');
    const refreshHistoryBtn = document.getElementById('refreshHistory');
    const noHistoryMessage = document.getElementById('noHistory');

    // Получение токена из localStorage
    const token = localStorage.getItem('access_token');
    const apiKey = localStorage.getItem('api_key');

    // Глобальные переменные для отложенной загрузки файловой активности
    // Эти переменные больше не используются, так как выводим сразу весь результат

    // Глобальные переменные для чанковой загрузки
    let fileActivityOffset = 0;
    const FILE_ACTIVITY_LIMIT = 500;
    let fileActivityTotal = 0;

    // Обработка перетаскивания файлов
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('drag-over');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('drag-over');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleFile(files[0]);
        }
    });

    // Обработка клика по зоне загрузки
    dropZone.addEventListener('click', () => {
        fileInput.click();
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFile(e.target.files[0]);
        }
    });

    async function handleFile(file) {
        console.log("Начало обработки файла:", file);
        // Показываем прогресс бар и секцию результатов
        progressBar.style.display = 'block';
        progress.style.width = '0%';
        resultsSection.style.display = 'block';
        statusSpinner.style.display = 'inline-block';
        analysisStatus.textContent = 'Загрузка файла...';
        console.log("все работает")

        const formData = new FormData();
        formData.append('file', file);

        try {
            // Отправляем файл
            console.log("Отправка файла...")
            const response = await fetch('/analyze', {
                method: 'POST',
                body: formData,
                headers: token ? {'Authorization': `Bearer ${token}`} : {}
            });
            console.log("Файл отправлен")

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || `Ошибка: ${response.status}`);
            }

            const data = await response.json();
            const runId = data.analysis_id;
            analysisStatus.textContent = 'Файл загружен. Открываем страницу анализа...';
            updateProgress(100);
            statusSpinner.style.display = 'none';

            console.log("Переходим на страницу /analysis/" + runId);
            window.location.href = `/analysis/${runId}`;
        } catch (error) {
            console.error('Error uploading file:', error);
            analysisStatus.textContent = 'Ошибка при загрузке файла: ' + error.message;
            analysisStatus.style.color = 'var(--error-color)';
            statusSpinner.style.display = 'none';
        }
    }

    function updateProgress(percent) {
        progress.style.width = `${percent}%`;
    }

    async function updateHistory() {
        try {
            const response = await fetch('/history');
            if (!response.ok) {
                throw new Error('Ошибка при получении истории');
            }
            const data = await response.json();
            const historyContainer = document.querySelector('.history-container');
            if (data.history && data.history.length) {
                historyContainer.innerHTML = '';
                data.history.forEach(item => {
                    const historyItem = document.createElement('div');
                    historyItem.classList.add('history-item');
                    if (item.status === 'running') {
                        historyItem.classList.add('running');
                    }
                    historyItem.setAttribute('data-analysis-id', item.analysis_id);
                    historyItem.innerHTML = `
                        <div class="history-item-header">
                            <span class="filename">${item.filename}</span>
                            <span class="timestamp">${item.timestamp}</span>
                        </div>
                        <div class="history-item-details">
                            <div class="status-indicator ${item.status}">${item.status}</div>
                            <button class="btn btn-sm btn-outline-secondary view-results-btn">Просмотреть результаты</button>
                        </div>
                    `;
                    historyContainer.appendChild(historyItem);
                });
                // Навешиваем обработчики на кнопки "Просмотреть результаты"
                document.querySelectorAll('.view-results-btn').forEach(btn => {
                    btn.addEventListener('click', function(e) {
                        const analysisId = e.target.closest('.history-item').dataset.analysisId;
                        window.location.href = '/analysis/' + analysisId;
                    });
                });
            } else {
                historyContainer.innerHTML = '<p>История анализов пуста</p>';
            }
        } catch (error) {
            console.error('Ошибка обновления истории:', error);
        }
    }

    // Обновление истории по нажатию кнопки "Обновить"
    if (refreshHistoryBtn) {
        refreshHistoryBtn.addEventListener('click', updateHistory);
    }

    // Обработка кнопок "Просмотреть результаты" для уже существующих элементов
    document.querySelectorAll('.view-results-btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
            const analysisId = e.target.closest('.history-item').dataset.analysisId;
            window.location.href = '/analysis/' + analysisId;
        });
    });

    // Функция, выполняющая одноразовый запрос для получения и отображения результатов
    async function showResults(analysisId) {
        console.log("Показываем результаты анализа:", analysisId);
        try {
            const response = await fetch(`/results/${analysisId}`, {
                headers: token ? { 'Authorization': `Bearer ${token}` } : {}
            });
            if (!response.ok) {
                console.log("Ошибка при получении результатов анализа:", response.status);
                if (response.status === 404) {
                    document.getElementById('fileActivityContent').textContent = 'Нет данных по файловой активности.';
                    document.getElementById('dockerOutputContent').textContent = 'Нет логов Docker.';
                    updateStatus('Нет данных');
                    return;
                } else {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
            }
            const data = await response.json();
            console.log("Получены результаты:", data);
            if (data.file_activity) {
                console.log("Количество элементов file_activity:", data.file_activity.length);
            } else {
                console.log("Поле file_activity отсутствует в полученных данных.");
            }
            updateStatus(window.analysisStatus || "running");

            // Обновляем логи Docker
            if (data.docker_output) {
                dockerOutputContent.textContent = data.docker_output;
            } else {
                dockerOutputContent.textContent = 'Нет логов Docker.';
            }
            const dockerLoader = document.getElementById('dockerOutputLoader');
            if (dockerLoader) dockerLoader.style.display = 'none';

            if (Array.isArray(data.file_activity) && data.file_activity.length > 0) {
                const preview = JSON.stringify(data.file_activity, null, 4);
                document.getElementById('fileActivityContent').textContent = preview;
                fileActivityTotal = data.total;
                fileActivityOffset = data.file_activity.length;
                if (fileActivityTotal > fileActivityOffset) {
                    updateLoadMoreButton(analysisId);
                }
                const remaining = fileActivityTotal - fileActivityOffset;
                const remainingSpan = document.getElementById('remainingCount');
                if (remainingSpan) {
                    remainingSpan.textContent = "Осталось элементов: " + remaining;
                }
            } else {
                document.getElementById('fileActivityContent').textContent = 'Нет данных по файловой активности.';
            }
            const loader = document.getElementById('fileActivityLoader');
            if (loader) loader.style.display = 'none';
        } catch (error) {
            console.error('Ошибка при получении результатов анализа:', error);
            analysisStatus.textContent = 'Ошибка при получении результатов анализа: ' + error.message;
            analysisStatus.style.color = 'var(--error-color)';
        }
    }

    // Опрос результатов анализа
    async function pollResults(analysisId) {
        // Вспомогательная функция для получения данных и обновления страницы
        async function fetchResultsAndUpdate(analysisId) {
            try {
                const response = await fetch(`/results/${analysisId}`, {
                    headers: token ? { 'Authorization': `Bearer ${token}` } : {}
                });
                if (!response.ok) {
                    if (response.status === 404) {
                        document.getElementById('fileActivityContent').textContent = 'Нет данных по файловой активности.';
                        document.getElementById('dockerOutputContent').textContent = 'Нет логов Docker.';
                        updateStatus('Нет данных');
                        return;
                    } else {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }
                }
                const data = await response.json();
                console.log("Получены результаты:", data);
                // Устанавливаем статус в соответствии с переданным значением
                updateStatus(window.analysisStatus || "running");
 
                // Обновляем логи Docker
                if (data.docker_output) {
                    dockerOutputContent.textContent = data.docker_output;
                } else {
                    dockerOutputContent.textContent = 'Нет логов Docker.';
                }
                const dockerLoader = document.getElementById('dockerOutputLoader');
                if (dockerLoader) dockerLoader.style.display = 'none';
 
                if (Array.isArray(data.file_activity) && data.file_activity.length > 0) {
                    // Форматируем данные с помощью JSON.stringify с отступом для красивого отображения
                    const preview = JSON.stringify(data.file_activity, null, 4);
                    // Используем innerHTML с заменой символов новой строки на <br/> для форматирования
                    document.getElementById('fileActivityContent').innerHTML = preview.replace(/\n/g, '<br/>');
                    fileActivityTotal = data.total;
                    fileActivityOffset = data.file_activity.length;
                    // Добавляем кнопки, если еще остались данные для подгрузки
                    if (fileActivityTotal > fileActivityOffset) {
                        updateLoadMoreButton(analysisId);
                    }
                } else {
                    document.getElementById('fileActivityContent').textContent = 'Нет данных по файловой активности.';
                }
                const loader = document.getElementById('fileActivityLoader');
                if (loader) loader.style.display = 'none';
            } catch (error) {
                console.error('Ошибка при получении результатов анализа:', error);
                analysisStatus.textContent = 'Ошибка при получении результатов анализа: ' + error.message;
                analysisStatus.style.color = 'var(--error-color)';
            }
        }

        // Немедленно загружаем результаты при открытии страницы
        await fetchResultsAndUpdate(analysisId);

        // Затем запускаем периодический опрос каждые 2 секунды
        const pollInterval = setInterval(async () => {
            await fetchResultsAndUpdate(analysisId);
        }, 2000);
    }

    // Обновление статуса анализа
    function updateStatus(status) {
        const statusElement = document.getElementById('analysisStatus');
        statusElement.textContent = `Статус: ${status}`;
        if (status === 'completed') {
            statusElement.style.color = 'var(--success-color)';
            statusSpinner.style.display = 'none';
        } else if (status === 'running') {
            statusElement.style.color = 'var(--warning-color)';
            statusSpinner.style.display = 'inline-block';
        } else {
            statusElement.style.color = 'var(--error-color)';
            statusSpinner.style.display = 'none';
        }
    }

    // Функция для загрузки следующего чанка
    async function loadNextChunk(analysisId, limitOverride) {
        try {
            const limit = limitOverride !== undefined ? limitOverride : FILE_ACTIVITY_LIMIT;
            const response = await fetch(`/results/${analysisId}/chunk?offset=${fileActivityOffset}&limit=${limit}`, {
                headers: token ? { 'Authorization': `Bearer ${token}` } : {}
            });
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            const pre = document.getElementById('fileActivityContent');
            // Дописываем новый чанк в существующий контент
            const existingContent = pre.textContent;
            const newContent = JSON.stringify(data.chunk, null, 4);
            pre.textContent = existingContent + "\n" + newContent;
            fileActivityOffset += data.chunk.length;
            updateLoadMoreButton(analysisId);
        } catch (error) {
            console.error('Ошибка при загрузке чанка:', error);
        }
    }

    // Функция для скачивания полного результата (переход на страницу скачивания)
    function downloadFullFile(analysisId) {
        window.location.assign(`/download/${analysisId}`);
    }

    // Функция для добавления кнопок загрузки оставшихся данных
    function updateLoadMoreButton(analysisId) {
        const container = document.getElementById('fileActivityContainer');
        let buttonArea = document.getElementById('buttonArea');
        if (!buttonArea) {
            buttonArea = document.createElement('div');
            buttonArea.id = 'buttonArea';
            buttonArea.style.display = 'flex';
            buttonArea.style.gap = '10px';
            buttonArea.style.marginTop = '10px';
            container.appendChild(buttonArea);
        }
        // Очистка области кнопок
        buttonArea.innerHTML = "";

        if (fileActivityTotal > fileActivityOffset) {
            const loadMoreBtn = document.createElement('button');
            loadMoreBtn.id = 'loadMoreBtn';
            loadMoreBtn.textContent = 'Загрузить ещё';
            loadMoreBtn.className = 'btn btn-secondary';
            loadMoreBtn.addEventListener('click', function() {
                loadNextChunk(analysisId);
            });
            buttonArea.appendChild(loadMoreBtn);

            const loadAllBtn = document.createElement('button');
            loadAllBtn.id = 'loadAllBtn';
            loadAllBtn.textContent = 'Загрузить всё';
            loadAllBtn.className = 'btn btn-primary';
            loadAllBtn.addEventListener('click', function() {
                downloadFullFile(analysisId);
            });
            buttonArea.appendChild(loadAllBtn);
        }
        // Обновляем отображение остатка элементов
        const remaining = fileActivityTotal - fileActivityOffset;
        const remainingSpan = document.getElementById('remainingCount');
        if (remainingSpan) {
            remainingSpan.textContent = "Осталось элементов: " + remaining;
        }
    }
    var x = window.A;
    console.log(x);

    // Если идентификатор анализа определён, загружаем результаты один раз при открытии страницы
    if (typeof analysisId !== "undefined" && analysisId) {
        console.log("Загружаем результаты анализа:", analysisId);
        // Загружаем результаты один раз (файловая активность фиксируется)
        showResults(analysisId);
        // // Каждые 2 секунды обновляем только Docker логи, не трогая файловую активность
        // setInterval(() => {
        //     updateDockerLogs(analysisId);
        // }, 5000);
    }

    // // Новая функция для обновления логов Docker
    // async function updateDockerLogs(analysisId) {
    //     try {
    //         const response = await fetch(`/results/${analysisId}`, {
    //             headers: token ? { 'Authorization': `Bearer ${token}` } : {}
    //         });
    //         if (!response.ok) {
    //             console.error("Ошибка при получении логов докера:", response.status);
    //             return;
    //         }
    //         const data = await response.json();
    //         if (data.docker_output) {
    //             dockerOutputContent.textContent = data.docker_output;
    //         } else {
    //             dockerOutputContent.textContent = 'Нет логов Docker.';
    //         }
    //         updateStatus("completed");
    //         const dockerLoader = document.getElementById('dockerOutputLoader');
    //         if (dockerLoader) dockerLoader.style.display = 'none';
    //     } catch (error) {
    //         console.error("Ошибка при обновлении логов докера:", error);
    //     }
    // }

    // Устанавливаем соединение с SSE эндпоинтом для обновлений
    const evtSource = new EventSource("/sse");
    evtSource.onmessage = function(event) {
        console.log("Получено SSE событие обновления:", event.data);
        try {
            const data = JSON.parse(event.data);
            // Если сообщение содержит поле 'redirect', перенаправляем пользователя
            if (data.redirect) {
                window.location.href = data.redirect;
            }
        } catch (e) {
            console.error("Ошибка обработки SSE события:", e);
        }
    };
});