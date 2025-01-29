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
        // Показываем прогресс бар и секцию результатов
        progressBar.style.display = 'block';
        progress.style.width = '0%';
        resultsSection.style.display = 'block';
        statusSpinner.style.display = 'inline-block';
        analysisStatus.textContent = 'Загрузка файла...';

        const formData = new FormData();
        formData.append('file', file);

        try {
            // Отправляем файл
            const response = await fetch('/analyze', {
                method: 'POST',
                body: formData,
                headers: token ? {'Authorization': `Bearer ${token}`} : {}
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || `Ошибка: ${response.status}`);
            }

            const data = await response.json();
            const runId = data.analysis_id;
            analysisStatus.textContent = 'Анализ запущен...';
            updateProgress(100);
            statusSpinner.style.display = 'none';

            // Обновляем историю
            await updateHistory();

            // Открываем результаты
            showResults(runId);
            pollResults(runId);
        } catch (error) {
            console.error('Error uploading file:', error);
            analysisStatus.textContent = 'Ошибка при загрузке файла';
            analysisStatus.style.color = 'var(--error-color)';
            statusSpinner.style.display = 'none';
        }
    }

    function updateProgress(percent) {
        progress.style.width = `${percent}%`;
    }

    async function updateHistory() {
        try {
            const response = await fetch('/history', {
                headers: token ? {'Authorization': `Bearer ${token}`} : {}
            });
            const data = await response.json();
            const historyContainer = document.querySelector('.history-container');
            
            if (data.history.length === 0) {
                historyContainer.innerHTML = '';
                noHistoryMessage.style.display = 'block';
                return;
            }

            noHistoryMessage.style.display = 'none';
            historyContainer.innerHTML = data.history.map(item => `
                <div class="history-item ${item.status === 'running' ? 'running' : ''}" 
                     data-analysis-id="${item.analysis_id}">
                    <div class="history-item-header">
                        <span class="filename">${item.filename}</span>
                        <span class="timestamp">${new Date(item.timestamp).toLocaleString()}</span>
                    </div>
                    <div class="history-item-details">
                        <div class="status-indicator ${item.status}">${item.status}</div>
                        <button class="btn btn-sm btn-outline-secondary view-results-btn">
                            Просмотреть результаты
                        </button>
                    </div>
                </div>
            `).join('');

            // Обновите обработчики для элементов истории
            document.querySelectorAll('.history-item').forEach(item => {
                const viewBtn = item.querySelector('.view-results-btn');
                const analysisId = item.dataset.analysisId;
                
                viewBtn.addEventListener('click', (e) => {
                    e.stopPropagation();  // Предотвращаем всплытие события
                    
                    // Удаляем активный класс у всех элементов
                    document.querySelectorAll('.history-item').forEach(i => 
                        i.classList.remove('active')
                    );
                    
                    // Добавляем активный класс текущему элементу
                    item.classList.add('active');
                    
                    showResults(analysisId);
                    pollResults(analysisId);
                    
                    // Обновляем URL
                    window.history.pushState(
                        { analysisId },
                        '',
                        `/analysis/${analysisId}`
                    );
                });
            });
        } catch (error) {
            console.error('Error updating history:', error);
        }
    }

    // Функция отображения результатов анализа
    async function showResults(analysisId) {
        try {
            const response = await fetch(`/results/${analysisId}`, {
                headers: token ? {'Authorization': `Bearer ${token}`} : {}
            });
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            updateStatus(data.status);
            if (data.docker_logs) {
                dockerOutputContent.textContent = data.docker_logs;
            }
            if (data.file_activity) {
                fileActivityContent.textContent = data.file_activity
                    .map(activity => {
                        let line = `${activity.Time} - ${activity.ProcessName} - ${activity.Operation}`;
                        if (activity.Path) line += ` - ${activity.Path}`;
                        if (activity.Detail) line += ` - ${activity.Detail}`;
                        return line;
                    })
                    .join('\n');
            }
        } catch (error) {
            console.error('Error showing results:', error);
            analysisStatus.textContent = 'Ошибка при получении результатов анализа';
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
        let attempts = 0;
        const maxAttempts = 30; // 1 минута
        const pollInterval = setInterval(async () => {
            try {
                const response = await fetch(`/results/${analysisId}`, {
                    headers: token ? {'Authorization': `Bearer ${token}`} : {}
                });
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                const data = await response.json();

                updateStatus(data.status);
                if (data.docker_logs) {
                    dockerOutputContent.textContent = data.docker_logs;
                }
                if (data.file_activity) {
                    fileActivityContent.textContent = data.file_activity
                        .map(activity => {
                            let line = `${activity.Time} - ${activity.ProcessName} - ${activity.Operation}`;
                            if (activity.Path) line += ` - ${activity.Path}`;
                            if (activity.Detail) line += ` - ${activity.Detail}`;
                            return line;
                        })
                        .join('\n');
                }

                if (data.status === 'completed' || data.status === 'error') {
                    clearInterval(pollInterval);
                }

                attempts += 1;
                if (attempts >= maxAttempts) {
                    clearInterval(pollInterval);
                    analysisStatus.textContent = 'Время ожидания истекло';
                    analysisStatus.style.color = 'var(--error-color)';
                }
            } catch (error) {
                console.error('Error polling results:', error);
                clearInterval(pollInterval);
                analysisStatus.textContent = 'Ошибка при опросе результатов анализа';
                analysisStatus.style.color = 'var(--error-color)';
            }
        }, 2000);
    }

    // Обновление истории при нажатии на кнопку
    refreshHistoryBtn.addEventListener('click', updateHistory);
});