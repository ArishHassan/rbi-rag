const chatHistory = document.getElementById('chatHistory');
const queryInput = document.getElementById('queryInput');
const sendBtn = document.getElementById('sendBtn');
const dropzone = document.getElementById('dropzone');
const fileInput = document.getElementById('fileInput');
const uploadStatus = document.getElementById('uploadStatus');
const rbiSearchInput = document.getElementById('rbiSearchInput');
const rbiSearchBtn = document.getElementById('rbiSearchBtn');
const rbiLatestBtn = document.getElementById('rbiLatestBtn');
const rbiReleaseList = document.getElementById('rbiReleaseList');
const rbiQueueBtn = document.getElementById('rbiQueueBtn');
const topRefreshBtn = document.getElementById('topRefreshBtn');
const topReleaseList = document.getElementById('topReleaseList');
const topQueueBtn = document.getElementById('topQueueBtn');
const clearSourcesBtn = document.getElementById('clearSourcesBtn');
const activeSources = document.getElementById('activeSources');
const topScopeChip = document.getElementById('topScopeChip');
const chatScopeLabel = document.getElementById('chatScopeLabel');
const urlInput = document.getElementById('urlInput');
const urlBtn = document.getElementById('urlBtn');

let historyData = [];
let rbiReleases = [];
let topReleases = [];
let selectedSearchIds = new Set();
let selectedTopIds = new Set();
let scopedSources = [];

function releaseKey(release) {
    return release.id || release.pdf_url || release.source_name;
}

function setStatus(message, color = '#607085') {
    uploadStatus.textContent = message;
    uploadStatus.style.color = color;
}

function addMessage(text, sender) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${sender}`;

    const bubble = document.createElement('div');
    bubble.className = 'bubble';
    bubble.textContent = text;

    msgDiv.appendChild(bubble);
    chatHistory.appendChild(msgDiv);
    chatHistory.scrollTop = chatHistory.scrollHeight;
}

function addTypingIndicator() {
    const msgDiv = document.createElement('div');
    msgDiv.className = 'message bot typing';
    msgDiv.id = 'typingIndicator';

    const indicator = document.createElement('div');
    indicator.className = 'typing-indicator';
    for (let i = 0; i < 3; i++) {
        const dot = document.createElement('div');
        dot.className = 'typing-dot';
        indicator.appendChild(dot);
    }

    msgDiv.appendChild(indicator);
    chatHistory.appendChild(msgDiv);
    chatHistory.scrollTop = chatHistory.scrollHeight;
}

function removeTypingIndicator() {
    const indicator = document.getElementById('typingIndicator');
    if (indicator) indicator.remove();
}

function renderReleaseList(container, releases, selectedIds, onToggle, emptyText) {
    container.innerHTML = '';

    if (!releases.length) {
        const empty = document.createElement('div');
        empty.className = 'release-empty';
        empty.textContent = emptyText;
        container.appendChild(empty);
        return;
    }

    releases.forEach((release, index) => {
        const key = releaseKey(release);
        const row = document.createElement('label');
        row.className = 'release-item';

        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.checked = selectedIds.has(key);
        checkbox.addEventListener('change', () => onToggle(key, checkbox.checked));

        const meta = document.createElement('div');
        meta.className = 'release-meta';

        const title = document.createElement('div');
        title.className = 'release-title';
        title.textContent = release.title;

        const details = document.createElement('div');
        details.className = 'release-date';
        const date = release.published_date || 'Date not shown';
        details.textContent = `${index + 1}. ${date}${release.size ? ' | ' + release.size : ''}`;

        meta.appendChild(title);
        meta.appendChild(details);
        row.appendChild(checkbox);
        row.appendChild(meta);
        container.appendChild(row);
    });
}

function updateQueueButtons() {
    rbiQueueBtn.disabled = selectedSearchIds.size === 0;
    topQueueBtn.disabled = selectedTopIds.size === 0;
}

function renderSearchReleases() {
    renderReleaseList(
        rbiReleaseList,
        rbiReleases,
        selectedSearchIds,
        (key, checked) => {
            if (checked) selectedSearchIds.add(key);
            else selectedSearchIds.delete(key);
            updateQueueButtons();
        },
        'Search or load latest releases.'
    );
    updateQueueButtons();
}

function renderTopReleases() {
    renderReleaseList(
        topReleaseList,
        topReleases,
        selectedTopIds,
        (key, checked) => {
            if (checked) selectedTopIds.add(key);
            else selectedTopIds.delete(key);
            updateQueueButtons();
        },
        'Latest releases will appear here.'
    );
    updateQueueButtons();
}

function renderActiveSources() {
    activeSources.innerHTML = '';

    if (!scopedSources.length) {
        activeSources.textContent = 'Chat scope: all indexed documents';
        topScopeChip.textContent = 'All indexed documents';
        chatScopeLabel.textContent = 'Using all indexed documents';
        clearSourcesBtn.disabled = true;
        return;
    }

    topScopeChip.textContent = `${scopedSources.length} selected source${scopedSources.length === 1 ? '' : 's'}`;
    chatScopeLabel.textContent = `Using ${scopedSources.length} selected RBI release${scopedSources.length === 1 ? '' : 's'}`;

    const label = document.createElement('div');
    label.className = 'scope-label';
    label.textContent = 'Selected sources';
    activeSources.appendChild(label);

    scopedSources.slice(0, 5).forEach((source) => {
        const pill = document.createElement('div');
        pill.className = 'source-pill';
        pill.textContent = source;
        activeSources.appendChild(pill);
    });

    if (scopedSources.length > 5) {
        const more = document.createElement('div');
        more.className = 'source-more';
        more.textContent = `+ ${scopedSources.length - 5} more`;
        activeSources.appendChild(more);
    }

    clearSourcesBtn.disabled = false;
}

async function loadRbiReleases(search = '', limit = 60) {
    setStatus('Loading RBI press releases...', '#607085');

    try {
        const url = new URL('/api/rbi-press-releases', window.location.origin);
        url.searchParams.set('limit', String(limit));
        if (search) url.searchParams.set('search', search);

        const res = await fetch(url);
        const data = await res.json();

        if (!res.ok) {
            setStatus(`Failed to load RBI releases: ${data.error}`, '#b42318');
            return [];
        }

        setStatus(`Loaded ${data.releases.length} RBI release(s).`, '#147d52');
        return data.releases || [];
    } catch (e) {
        setStatus('Failed to reach RBI release service. Open the app through the local server.', '#b42318');
        return [];
    }
}

async function loadSearchResults(search = '') {
    rbiReleaseList.innerHTML = '';
    rbiReleases = await loadRbiReleases(search, 60);
    selectedSearchIds = new Set();
    renderSearchReleases();
}

async function loadTopFive() {
    topReleaseList.innerHTML = '';
    topReleases = await loadRbiReleases('', 5);
    selectedTopIds = new Set();
    renderTopReleases();
}

async function queueReleases(releases) {
    if (!releases.length) return;

    setStatus('Queueing selected RBI releases...', '#607085');

    try {
        const res = await fetch('/api/rbi-press-releases/queue', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ releases })
        });
        const data = await res.json();

        if (!res.ok) {
            setStatus(`Failed to queue releases: ${data.error}`, '#b42318');
            return;
        }

        scopedSources = data.sources || [];
        historyData = [];
        renderActiveSources();
        setStatus(`${data.message} Chat is scoped after indexing completes.`, '#147d52');
    } catch (e) {
        setStatus('Failed to queue selected RBI releases.', '#b42318');
    }
}

async function handleSend() {
    const query = queryInput.value.trim();
    if (!query) return;

    queryInput.value = '';
    queryInput.style.height = 'auto';

    addMessage(query, 'user');
    addTypingIndicator();

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query, history: historyData, sources: scopedSources })
        });

        const data = await response.json();
        removeTypingIndicator();

        if (response.ok) {
            addMessage(data.answer, 'bot');
            historyData.push({ role: 'user', content: query });
            historyData.push({ role: 'assistant', content: data.answer });
        } else {
            addMessage(`Error: ${data.error}`, 'bot');
        }
    } catch (e) {
        removeTypingIndicator();
        addMessage('Network error. Open the app through the local server.', 'bot');
    }
}

async function handleFiles(files) {
    for (const file of files) {
        if (!file.name.toLowerCase().endsWith('.pdf') && !file.name.toLowerCase().endsWith('.json')) {
            setStatus('Only PDF and JSON files are allowed.', '#b42318');
            continue;
        }

        setStatus(`Uploading ${file.name}...`, '#607085');

        const formData = new FormData();
        formData.append('file', file);

        try {
            const res = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();

            if (res.ok) setStatus(`${file.name} queued.`, '#147d52');
            else setStatus(data.error, '#b42318');
        } catch (e) {
            setStatus('Upload failed.', '#b42318');
        }
    }
}

queryInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
    }
});

queryInput.addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = `${this.scrollHeight}px`;
});

sendBtn.addEventListener('click', handleSend);

dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('dragover');
});

dropzone.addEventListener('dragleave', () => {
    dropzone.classList.remove('dragover');
});

dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('dragover');
    if (e.dataTransfer.files.length > 0) handleFiles(e.dataTransfer.files);
});

fileInput.addEventListener('change', () => {
    if (fileInput.files.length > 0) handleFiles(fileInput.files);
});

urlBtn.addEventListener('click', async () => {
    const url = urlInput.value.trim();
    if (!url) return;

    if (!url.startsWith('http')) {
        setStatus('Enter a valid http or https URL.', '#b42318');
        return;
    }

    setStatus('Queueing URL...', '#607085');

    try {
        const res = await fetch('/api/upload-url', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });
        const data = await res.json();

        if (res.ok) {
            setStatus('URL queued for ingestion.', '#147d52');
            urlInput.value = '';
        } else {
            setStatus(data.error, '#b42318');
        }
    } catch (e) {
        setStatus('Failed to submit URL.', '#b42318');
    }
});

rbiLatestBtn.addEventListener('click', () => loadSearchResults());
rbiSearchBtn.addEventListener('click', () => loadSearchResults(rbiSearchInput.value.trim()));
rbiSearchInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        e.preventDefault();
        loadSearchResults(rbiSearchInput.value.trim());
    }
});

rbiQueueBtn.addEventListener('click', () => {
    const selected = rbiReleases.filter((release) => selectedSearchIds.has(releaseKey(release)));
    queueReleases(selected);
});

topRefreshBtn.addEventListener('click', loadTopFive);
topQueueBtn.addEventListener('click', () => {
    const selected = topReleases.filter((release) => selectedTopIds.has(releaseKey(release)));
    queueReleases(selected);
});

clearSourcesBtn.addEventListener('click', () => {
    scopedSources = [];
    historyData = [];
    renderActiveSources();
    setStatus('Chat scope reset to all indexed documents.', '#607085');
});

renderSearchReleases();
renderTopReleases();
renderActiveSources();
loadTopFive();
