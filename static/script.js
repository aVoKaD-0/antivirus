document.addEventListener('DOMContentLoaded', function() {
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
    const FILE_ACTIVITY_LIMIT = 100;
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

    // Функция отображения результатов анализа
    async function showResults(analysisId) {
        try {
            const response = await fetch(`/results/${analysisId}`, {
                headers: token ? { 'Authorization': `Bearer ${token}` } : {}
            });
            if (!response.ok) {
                if (response.status === 404) {
                    fileActivityContent.textContent = 'Нет данных по файловой активности.';
                    dockerOutputContent.textContent = 'Нет логов Docker.';
                    updateStatus('Нет данных');
                    return;
                } else {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
            }
            const data = await response.json();
            updateStatus(data.status || 'неизвестно');

            // Вывод логов Docker
            if (data.docker_output) {
                dockerOutputContent.textContent = data.docker_output;
            } else {
                dockerOutputContent.textContent = 'Нет логов Docker.';
            }
            const dockerLoader = document.getElementById('dockerOutputLoader');
            if (dockerLoader) dockerLoader.style.display = 'none';

            // Вывод файловой активности: при завершённом анализе выводим сразу весь результат
            if (Array.isArray(data.file_activity) && data.file_activity.length > 0) {
                document.getElementById('fileActivityContent').textContent =
                    JSON.stringify(data.file_activity, null, 2);
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

    // Опрос результатов анализа
    async function pollResults(analysisId) {
        let lastPreview = "";
        const pollInterval = setInterval(async () => {
            try {
                const response = await fetch(`/results/${analysisId}`);
                if (!response.ok) {
                    if (response.status === 404) {
                        document.getElementById('fileActivityContent').textContent = 'Нет данных по файловой активности.';
                        document.getElementById('dockerOutputContent').textContent = 'Нет логов Docker.';
                        clearInterval(pollInterval);
                        return;
                    } else {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }
                }
                const data = await response.json();
                console.log(data);
                
                const statusText = data.status === 'running' ? 'Анализ выполняется' :
                                   data.status === 'completed' ? 'Анализ завершен' : 'Анализ остановлен';
                document.getElementById('analysisStatus').textContent = statusText;

                if (Array.isArray(data.file_activity) && data.file_activity.length > 0) {
                    const previewCount = Math.min(data.file_activity.length, 50);
                    const newPreview = JSON.stringify(data.file_activity.slice(0, previewCount), null, 2);
                    if (data.status === 'completed') {
                        clearInterval(pollInterval);
                        document.getElementById('fileActivityContent').textContent = newPreview;
                        fileActivityTotal = data.file_activity.length;
                        fileActivityOffset = previewCount;
                        updateLoadMoreButton(analysisId);
                    } else {
                        if (newPreview !== lastPreview) {
                            document.getElementById('fileActivityContent').textContent = newPreview;
                            lastPreview = newPreview;
                        }
                    }
                } else {
                    document.getElementById('fileActivityContent').textContent = 'Нет данных по файловой активности.';
                }

                // Вывод логов Docker
                document.getElementById('dockerOutputContent').textContent =
                    data.docker_output ? data.docker_output : 'Нет логов Docker.';
                const dockerLoader = document.getElementById('dockerOutputLoader');
                if (dockerLoader) dockerLoader.style.display = 'none';

                // Если статус становится "stopped" или "error", также останавливаем опрос.
                if (data.status === 'stopped' || data.status === 'error') {
                    clearInterval(pollInterval);
                }

                // Скрываем спиннер загрузки файловой активности после обновления превью
                const fileLoader = document.getElementById('fileActivityLoader');
                if (fileLoader) fileLoader.style.display = 'none';
            } catch (error) {
                console.error('Ошибка при опросе результатов:', error);
            }
        }, 2000);
    }

    // Если мы находимся на странице анализа (analysisId передается как глобальная переменная)
    if (typeof analysisId !== 'undefined' && analysisId) {
        pollResults(analysisId);
    }

    async function loadFullFile(analysisId) {
        try {
            const response = await fetch(`/results/${analysisId}`, {
                headers: token ? { 'Authorization': `Bearer ${token}` } : {}
            });
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            // Если данные есть, выводим весь результат файловой активности
            if (Array.isArray(data.file_activity) && data.file_activity.length > 0) {
                document.getElementById('fileActivityContent').textContent =
                    JSON.stringify(data.file_activity, null, 2);
            } else {
                document.getElementById('fileActivityContent').textContent = 'Нет данных по файловой активности.';
            }
        } catch (error) {
            console.error('Ошибка при загрузке полного файла:', error);
        }
    }

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
            fileActivityTotal = data.total;
            const pre = document.getElementById('fileActivityContent');
            // Если это первый чанк, перезаписываем содержимое, иначе – добавляем с новой строки
            if (fileActivityOffset === 0) {
                pre.textContent = JSON.stringify(data.chunk, null, 2);
            } else {
                pre.textContent += "\n" + JSON.stringify(data.chunk, null, 2);
            }
            fileActivityOffset += data.chunk.length;
            // Скрываем элемент загрузки файловой активности после получения данных чанка
            const loader = document.getElementById('fileActivityLoader');
            if (loader) loader.style.display = 'none';
            updateLoadMoreButton(analysisId);
        } catch (error) {
            console.error("Ошибка при загрузке чанка:", error);
        }
    }

    async function loadAllChunks(analysisId) {
        try {
            let loadAllBtn = document.getElementById("loadAllBtn");
            if (loadAllBtn) loadAllBtn.disabled = true;
            const remaining = fileActivityTotal - fileActivityOffset;
            if (remaining > 0) {
                // Загружаем остаток за один запрос
                await loadNextChunk(analysisId, remaining);
            }
            // Если данные полностью загружены, updateLoadMoreButton удалит кнопки.
        } catch (error) {
            console.error("Ошибка при загрузке всех чанков:", error);
        }
    }

    function updateLoadMoreButton(analysisId) {
        const remaining = fileActivityTotal - fileActivityOffset;
        const container = document.getElementById('fileActivityContainer');

        // Создаем контейнер для кнопок, если его ещё нет
        let buttonArea = document.getElementById("buttonArea");
        if (!buttonArea) {
            buttonArea = document.createElement("div");
            buttonArea.id = "buttonArea";
            // Используем flex для горизонтального расположения кнопок
            buttonArea.style.display = "flex";
            buttonArea.style.alignItems = "center";
            buttonArea.style.marginTop = "0.5rem";
            container.appendChild(buttonArea);
        }

        let btn = document.getElementById("loadMoreBtn");
        let loadAllBtn = document.getElementById("loadAllBtn");
        let remainingElement = document.getElementById("remainingCount");

        if (remaining > 0) {
            if (!btn) {
                btn = document.createElement('button');
                btn.id = "loadMoreBtn";
                btn.textContent = "Загрузить ещё";
                btn.className = "btn btn-secondary";
                btn.addEventListener("click", function() { loadNextChunk(analysisId); });
                buttonArea.appendChild(btn);
            }
            if (!loadAllBtn) {
                loadAllBtn = document.createElement('button');
                loadAllBtn.id = "loadAllBtn";
                loadAllBtn.textContent = "Загрузить всё";
                loadAllBtn.className = "btn btn-primary ms-2";
                loadAllBtn.addEventListener("click", function() { downloadFullFile(analysisId); });
                buttonArea.appendChild(loadAllBtn);
            }
            if (!remainingElement) {
                remainingElement = document.createElement('div');
                remainingElement.id = "remainingCount";
                remainingElement.className = "text-muted ms-2";
                buttonArea.appendChild(remainingElement);
            }
            remainingElement.textContent = "Осталось загрузить: " + remaining + " строк";
        } else {
            if (buttonArea) {
                buttonArea.remove();
            }
        }
    }

    function downloadFullFile(analysisId) {
        const downloadUrl = `/download/${analysisId}`;
        console.log("Redirecting to:", downloadUrl);
        window.location.assign(downloadUrl);
    }

});
