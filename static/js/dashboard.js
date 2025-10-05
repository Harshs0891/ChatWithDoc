// Global variables
let pdfDocument = null;
let documentProcessed = false;
let currentScale = 1.2;
let currentPage = 1;
let totalPages = 1;
let currentHighlights = [];
let pageTextContent = {};
let pageTextMapping = {};
let isProcessingMessage = false;

// Wait for DOM to be fully loaded
document.addEventListener('DOMContentLoaded', function () {
    console.log('DOM loaded, initializing...');
    initializeApplication();
});

function initializeApplication() {
    // Setup file input handler
    const fileInput = document.getElementById('file-input');
    if (fileInput) {
        console.log('File input found, adding listener');
        fileInput.addEventListener('change', handleFileSelect);
    } else {
        console.error('File input not found!');
    }

    // Setup all click handlers for file selection
    const selectFileBtn = document.getElementById('select-file-btn');
    if (selectFileBtn) {
        selectFileBtn.addEventListener('click', function (e) {
            e.preventDefault();
            console.log('Select file button clicked');
            if (fileInput) fileInput.click();
        });
    }

    const uploadCompactBtn = document.getElementById('upload-compact-btn');
    if (uploadCompactBtn) {
        uploadCompactBtn.addEventListener('click', function (e) {
            e.preventDefault();
            console.log('Upload compact button clicked');
            if (fileInput) fileInput.click();
        });
    }

    const dropZone = document.getElementById('drop-zone');
    if (dropZone) {
        dropZone.addEventListener('click', function (e) {
            e.preventDefault();
            console.log('Drop zone clicked');
            if (fileInput) fileInput.click();
        });

        // Setup drag and drop
        setupDragAndDrop(dropZone);
    }

    // Setup chat handlers
    const sendButton = document.getElementById('send-button');
    const messageInput = document.getElementById('message-input');

    if (sendButton) {
        sendButton.addEventListener('click', sendMessage);
    }

    if (messageInput) {
        messageInput.addEventListener('keypress', function (e) {
            if (e.key === 'Enter' && !isProcessingMessage) {
                sendMessage();
            }
        });
    }

    // Setup page navigation
    const prevPageBtn = document.getElementById('prev-page');
    const nextPageBtn = document.getElementById('next-page');

    if (prevPageBtn) {
        prevPageBtn.addEventListener('click', goToPrevPage);
    }

    if (nextPageBtn) {
        nextPageBtn.addEventListener('click', goToNextPage);
    }

    // New session button
    const newSessionBtn = document.getElementById('new-session-btn');
    if (newSessionBtn) {
        newSessionBtn.addEventListener('click', function () {
            if (confirm('Start a new session? This will clear the current document and chat.')) {
                location.reload();
            }
        });
    }

    console.log('Application initialized successfully');
}

function setupDragAndDrop(dropZone) {
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, preventDefaults, false);
        document.body.addEventListener(eventName, preventDefaults, false);
    });

    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, highlight, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, unhighlight, false);
    });

    dropZone.addEventListener('drop', handleDrop, false);

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    function highlight(e) {
        dropZone.classList.add('drag-over');
    }

    function unhighlight(e) {
        dropZone.classList.remove('drag-over');
    }

    function handleDrop(e) {
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            console.log('File dropped:', files[0].name);
            handleFile(files[0]);
        }
    }
}

function handleFileSelect(e) {
    const file = e.target.files[0];
    if (file) {
        console.log('File selected:', file.name);
        handleFile(file);
    }
}

function handleFile(file) {
    console.log('Handling file:', file.name, 'Type:', file.type);

    if (file.type !== 'application/pdf') {
        showError('Please upload a PDF file only. Selected file type: ' + file.type);
        return;
    }

    processFile(file);
}

async function processFile(file) {
    console.log('Starting to process file:', file.name);

    try {
        showProcessingState();

        // Update progress - Step 1: Upload
        updateProcessingStep('step-upload', 'active');
        updateProgressBar(10);

        // Small delay for UI update
        await sleep(500);

        // Extract text from PDF
        console.log('Extracting text from PDF...');
        updateProgressBar(25);
        updateProcessingStep('step-upload', 'completed');
        updateProcessingStep('step-extract', 'active');

        await extractFullPdfText(file);

        updateProgressBar(50);
        updateProcessingStep('step-extract', 'completed');
        updateProcessingStep('step-analyze', 'active');

        // Upload to server
        console.log('Uploading to server...');
        const formData = new FormData();
        formData.append('file', file);

        const response = await fetch('/process-pdf', {
            method: 'POST',
            body: formData
        });

        console.log('Server response status:', response.status);
        updateProgressBar(80);

        if (!response.ok) {
            throw new Error(`Server error: ${response.status}`);
        }

        const result = await response.json();
        console.log('Server response:', result);

        if (result.success) {
            updateProgressBar(90);
            updateProcessingStep('step-analyze', 'completed');
            updateProcessingStep('step-complete', 'active');

            // Render PDF
            await renderPDF(file);

            updateProgressBar(100);
            await sleep(500);
            updateProcessingStep('step-complete', 'completed');

            // Complete processing
            completeProcessing(file.name);
            setupChatInterface(file.name, result);

        } else {
            throw new Error(result.message || 'Failed to process PDF');
        }

    } catch (error) {
        console.error('Error processing file:', error);
        showError('Error processing file: ' + error.message);
        resetUploadState();
    }
}

function showProcessingState() {
    console.log('Showing processing state');

    const uploadSection = document.getElementById('upload-section');
    const processingContainer = document.getElementById('processing-container');
    const uploadBar = document.getElementById('upload-bar');
    const uploadStatus = document.getElementById('upload-status');
    const processingSteps = document.getElementById('processing-steps');
    const uploadCompactBtn = document.getElementById('upload-compact-btn');

    if (uploadSection) {
        uploadSection.style.display = 'none';
    }

    if (processingContainer) {
        processingContainer.style.display = 'block';
    }

    if (uploadBar) {
        uploadBar.classList.add('processing');
    }

    if (uploadStatus) {
        uploadStatus.innerHTML = '<i class="fas fa-spinner fa-spin"></i><span>Processing document...</span>';
    }

    if (processingSteps) {
        processingSteps.classList.add('active');
    }

    if (uploadCompactBtn) {
        uploadCompactBtn.disabled = true;
    }

    updateProgressBar(0);
}

function updateProcessingStep(stepId, status) {
    const step = document.getElementById(stepId);
    if (!step) return;

    step.classList.remove('active', 'completed');

    if (status === 'active') {
        step.classList.add('active');
        const icon = step.querySelector('i');
        if (icon) {
            icon.className = 'fas fa-spinner fa-spin';
        }
    } else if (status === 'completed') {
        step.classList.add('completed');
        const icon = step.querySelector('i');
        if (icon) {
            icon.className = 'fas fa-check-circle';
        }
    }
}

function updateProgressBar(percentage) {
    const progressBar = document.getElementById('progress-bar');
    if (progressBar) {
        progressBar.style.width = `${percentage}%`;
    }
}

function completeProcessing(filename) {
    console.log('Completing processing for:', filename);

    const processingContainer = document.getElementById('processing-container');
    const uploadBar = document.getElementById('upload-bar');
    const uploadStatus = document.getElementById('upload-status');
    const uploadCompactBtn = document.getElementById('upload-compact-btn');

    setTimeout(() => {
        if (processingContainer) {
            processingContainer.style.display = 'none';
        }

        if (uploadBar) {
            uploadBar.classList.remove('processing');
        }

        if (uploadStatus) {
            uploadStatus.innerHTML = `
                <i class="fas fa-check-circle" style="color: var(--success-color);"></i>
                <span style="color: var(--success-color); font-weight: 600;">Document loaded: ${filename}</span>
            `;
        }

        if (uploadCompactBtn) {
            uploadCompactBtn.innerHTML = '<i class="fas fa-sync-alt"></i><span>Change PDF</span>';
            uploadCompactBtn.disabled = false;
        }
    }, 1000);
}

function resetUploadState() {
    console.log('Resetting upload state');

    const processingContainer = document.getElementById('processing-container');
    const uploadBar = document.getElementById('upload-bar');
    const uploadStatus = document.getElementById('upload-status');
    const uploadCompactBtn = document.getElementById('upload-compact-btn');
    const uploadSection = document.getElementById('upload-section');

    if (processingContainer) {
        processingContainer.style.display = 'none';
    }

    if (uploadBar) {
        uploadBar.classList.remove('processing');
    }

    if (uploadStatus) {
        uploadStatus.innerHTML = '<i class="fas fa-exclamation-triangle" style="color: var(--danger-color);"></i><span>Upload failed. Please try again.</span>';
    }

    if (uploadCompactBtn) {
        uploadCompactBtn.disabled = false;
    }

    if (uploadSection) {
        uploadSection.style.display = 'flex';
    }
}

async function extractFullPdfText(file) {
    try {
        const arrayBuffer = await file.arrayBuffer();
        const loadingTask = pdfjsLib.getDocument({ data: arrayBuffer });
        const pdf = await loadingTask.promise;

        console.log('PDF loaded, pages:', pdf.numPages);

        for (let pageNum = 1; pageNum <= pdf.numPages; pageNum++) {
            const page = await pdf.getPage(pageNum);
            const textContent = await page.getTextContent();

            const pageText = textContent.items
                .map(item => item.str)
                .join(' ')
                .replace(/\s+/g, ' ')
                .trim();

            pageTextContent[pageNum] = pageText;

            pageTextMapping[pageNum] = textContent.items.map(item => ({
                text: item.str,
                transform: item.transform,
                width: item.width,
                height: item.height
            }));
        }

        console.log('Text extraction complete');
    } catch (error) {
        console.error('Error extracting text:', error);
    }
}

async function renderPDF(file) {
    try {
        const arrayBuffer = await file.arrayBuffer();
        const loadingTask = pdfjsLib.getDocument({ data: arrayBuffer });

        pdfDocument = await loadingTask.promise;
        totalPages = pdfDocument.numPages;
        currentPage = 1;

        console.log('Rendering PDF, total pages:', totalPages);

        const pageNavigation = document.getElementById('page-navigation');
        if (pageNavigation) {
            pageNavigation.style.display = 'flex';
        }

        updatePageControls();
        await renderPage(currentPage);

    } catch (error) {
        console.error('Error rendering PDF:', error);
    }
}

async function renderPage(pageNum) {
    if (!pdfDocument || pageNum < 1 || pageNum > totalPages) return;

    const pdfContent = document.getElementById('pdf-content');
    if (!pdfContent) return;

    pdfContent.innerHTML = '';

    try {
        const page = await pdfDocument.getPage(pageNum);
        const viewport = page.getViewport({ scale: currentScale });

        const canvas = document.createElement('canvas');
        const context = canvas.getContext('2d');
        canvas.height = viewport.height;
        canvas.width = viewport.width;
        canvas.className = 'pdf-page';

        await page.render({ canvasContext: context, viewport }).promise;

        pdfContent.appendChild(canvas);
        currentPage = pageNum;
        updatePageControls();

    } catch (error) {
        console.error('Error rendering page:', error);
    }
}

function updatePageControls() {
    const pageInfo = document.getElementById('page-info');
    const prevPageBtn = document.getElementById('prev-page');
    const nextPageBtn = document.getElementById('next-page');

    if (pageInfo) {
        pageInfo.textContent = `Page ${currentPage} of ${totalPages}`;
    }

    if (prevPageBtn) {
        prevPageBtn.disabled = currentPage <= 1;
    }

    if (nextPageBtn) {
        nextPageBtn.disabled = currentPage >= totalPages;
    }
}

async function goToPrevPage() {
    if (currentPage > 1) {
        await renderPage(currentPage - 1);
    }
}

async function goToNextPage() {
    if (currentPage < totalPages) {
        await renderPage(currentPage + 1);
    }
}

async function goToPage(pageNum) {
    pageNum = parseInt(pageNum);
    if (pageNum >= 1 && pageNum <= totalPages && pageNum !== currentPage) {
        await renderPage(pageNum);
    }
}

async function setupChatInterface(filename, result) {
    console.log('Setting up chat interface');

    const uploadSection = document.getElementById('upload-section');
    const pdfViewer = document.getElementById('pdf-viewer');
    const pdfFilename = document.getElementById('pdf-filename');
    const messageInput = document.getElementById('message-input');
    const sendButton = document.getElementById('send-button');
    const newSessionBtn = document.getElementById('new-session-btn');

    if (uploadSection) {
        uploadSection.style.display = 'none';
    }

    if (pdfViewer) {
        pdfViewer.style.display = 'flex';
    }

    if (pdfFilename) {
        pdfFilename.textContent = filename;
    }

    if (messageInput) {
        messageInput.disabled = false;
    }

    if (sendButton) {
        sendButton.disabled = false;
    }

    if (newSessionBtn) {
        newSessionBtn.style.display = 'inline-flex';
    }

    documentProcessed = true;

    // Show welcome message
    await generateInitialOverview();
}

async function generateInitialOverview() {
    showTypingIndicator();

    try {
        const response = await fetch('/document-summary', {
            method: 'GET',
            headers: { 'Content-Type': 'application/json' }
        });

        const result = await response.json();
        hideTypingIndicator();

        if (result.success) {
            const formattedOverview = formatOverviewMessage(result.summary, result.questions || []);
            addMessage('ai', formattedOverview);
        } else {
            const welcomeMessage = `
                <strong>Document Ready!</strong><br><br>
                Your PDF has been loaded successfully. I'm ready to answer any questions about the content.
            `;
            addMessage('ai', welcomeMessage);
        }
    } catch (error) {
        console.error('Error getting overview:', error);
        hideTypingIndicator();
        const welcomeMessage = `
            <strong>Document Ready!</strong><br><br>
            Your PDF has been loaded successfully. Feel free to ask me any questions about it!
        `;
        addMessage('ai', welcomeMessage);
    }
}

function formatOverviewMessage(summary, questions) {
    const cleanSummary = summary.replace(/\*/g, "");

    const hour = new Date().getHours();
    let greeting = hour < 12 ? "Good Morning" : hour < 18 ? "Good Afternoon" : "Good Evening";

    let html = `<strong>${greeting}!</strong><br><br>${cleanSummary}`;

    if (questions && questions.length > 0) {
        html += `<br><br><strong>You might want to ask:</strong><br><br>`;
        questions.forEach(question => {
            html += `<div class="suggested-question" onclick="askSuggestedQuestion('${question.replace(/'/g, "\\'")}')">${question}</div>`;
        });
    }

    return html;
}

async function sendMessage() {
    const messageInput = document.getElementById('message-input');
    const sendButton = document.getElementById('send-button');

    if (!messageInput || !sendButton) return;

    const message = messageInput.value.trim();
    if (!message || !documentProcessed || isProcessingMessage) return;

    isProcessingMessage = true;
    sendButton.disabled = true;

    addMessage('user', message);
    messageInput.value = '';
    showTypingIndicator();

    try {
        const response = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: message,
                pdf_only: true
            })
        });

        const result = await response.json();
        hideTypingIndicator();

        if (result.success) {
            const formattedAnswer = formatAIResponse(result.answer);
            addMessage('ai', formattedAnswer);
        } else {
            addMessage('ai', 'Error: ' + (result.message || 'Unable to process your request'));
        }
    } catch (error) {
        console.error('Chat error:', error);
        hideTypingIndicator();
        addMessage('ai', 'Error: Unable to connect to server. Please try again.');
    } finally {
        isProcessingMessage = false;
        sendButton.disabled = false;
        messageInput.focus();
    }
}

function formatAIResponse(answer) {
    answer = answer.replace(/\*/g, '').trim();
    const sentences = answer.split(/(?<=[.!?])\s+/).filter(s => s.trim().length > 0);

    let html = '';
    sentences.forEach(sentence => {
        sentence = sentence.trim();
        if (!sentence) return;

        if (sentence.match(/^[•\-]|^\d+\./)) {
            const content = sentence.replace(/^[•\-]\s*|^\d+\.\s*/, '');
            const pageNum = findPageForText(content);
            html += `
                <div style="display: flex; align-items: start; justify-content: space-between; margin: 8px 0;">
                    <span style="flex: 1;">• ${content}</span>
                    <span class="page-ref" onclick="goToPage(${pageNum})">${pageNum}</span>
                </div>
            `;
        } else {
            if (sentence.toLowerCase().includes("don't have information")) {
                html += `<p style="margin: 8px 0;">${sentence}</p>`;
            } else {
                const pageNum = findPageForText(sentence);
                html += `
                    <div style="display: flex; align-items: start; justify-content: space-between; margin: 8px 0;">
                        <span style="flex: 1;">${sentence}</span>
                        <span class="page-ref" onclick="goToPage(${pageNum})">${pageNum}</span>
                    </div>
                `;
            }
        }
    });

    return html;
}

function findPageForText(searchText) {
    if (!searchText || !pageTextContent) return 1;

    const cleanSearch = searchText.toLowerCase().trim();
    const meaningfulWords = cleanSearch
        .replace(/[^\w\s]/g, ' ')
        .split(/\s+/)
        .filter(word => word.length > 3);

    if (meaningfulWords.length === 0) return 1;

    let bestMatch = { page: 1, score: 0 };

    for (let pageNum = 1; pageNum <= totalPages; pageNum++) {
        const pageText = pageTextContent[pageNum];
        if (!pageText) continue;

        const pageTextLower = pageText.toLowerCase();
        let score = 0;

        if (pageTextLower.includes(cleanSearch)) {
            score += 100;
        }

        meaningfulWords.forEach(word => {
            if (pageTextLower.includes(word)) {
                score += 10;
            }
        });

        if (score > bestMatch.score) {
            bestMatch = { page: pageNum, score: score };
        }
    }

    return bestMatch.score > 0 ? bestMatch.page : 1;
}

function addMessage(sender, content) {
    const messagesContainer = document.getElementById('messages-container');
    const emptyState = document.getElementById('empty-state');

    if (!messagesContainer) return;

    if (emptyState && emptyState.style.display !== 'none') {
        emptyState.style.display = 'none';
    }

    const messageDiv = document.createElement('div');
    const timestamp = new Date().toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit'
    });

    if (sender === 'user') {
        messageDiv.className = 'user-message';
        messageDiv.innerHTML = `
            <div class="message-content">
                <div>${content}</div>
                <div class="message-time">${timestamp}</div>
            </div>
        `;
    } else {
        messageDiv.className = 'ai-message';
        messageDiv.innerHTML = `
            <div class="message-content">
                <div class="message-header">
                    <span>AI Assistant</span>
                </div>
                <div class="message-body">${content}</div>
                <div class="message-time">${timestamp}</div>
            </div>
        `;
    }

    messagesContainer.appendChild(messageDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function showTypingIndicator() {
    const typingIndicator = document.getElementById('typing-indicator');
    if (typingIndicator) {
        typingIndicator.classList.add('active');
    }
}

function hideTypingIndicator() {
    const typingIndicator = document.getElementById('typing-indicator');
    if (typingIndicator) {
        typingIndicator.classList.remove('active');
    }
}

function showError(message) {
    console.error('Error:', message);

    const uploadStatus = document.getElementById('upload-status');
    if (uploadStatus) {
        uploadStatus.innerHTML = `
            <i class="fas fa-exclamation-triangle" style="color: var(--danger-color);"></i>
            <span style="color: var(--danger-color);">${message}</span>
        `;
    }

    alert(message); // Also show alert for immediate feedback
    resetUploadState();
}

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// Global functions for onclick handlers
window.goToPage = goToPage;
window.askSuggestedQuestion = function (question) {
    if (isProcessingMessage) return;

    const messageInput = document.getElementById('message-input');
    if (messageInput) {
        messageInput.value = question;
        sendMessage();
    }
};

console.log('Dashboard script loaded');