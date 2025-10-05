// History Management - Fixed for persistent data
// This file properly integrates with your Flask backend endpoints

(function () {
    'use strict';

    // Configuration
    const CONFIG = {
        DEBUG_MODE: true,
        REFRESH_INTERVAL: 30000, // 30 seconds
        ENDPOINTS: {
            USER_SESSIONS: '/user-sessions',
            LOAD_SESSION: '/load-session',
            DELETE_SESSION: '/delete-session',
            RENAME_SESSION: '/rename-session',
            CLEAR_ALL: '/clear-all-sessions',
            SESSION_MESSAGES: '/session/{id}/messages',
            SESSION_PDF: '/session/{id}/pdf'
        }
    };

    // State management
    let state = {
        sessions: [],
        currentSessionId: null,
        isLoading: false,
        refreshTimer: null
    };

    // Debug logging
    function debugLog(message, data = null) {
        if (CONFIG.DEBUG_MODE) {
            if (data) {
                console.log(`[History] ${message}:`, data);
            } else {
                console.log(`[History] ${message}`);
            }
        }
    }

    // Initialize history sidebar
    function initializeHistorySidebar() {
        debugLog('Initializing history sidebar');

        // Setup sidebar toggle
        setupSidebarToggle();

        // Setup clear history button
        setupClearHistoryButton();

        // Load initial sessions
        loadUserSessions();

        // Setup auto-refresh
        if (CONFIG.REFRESH_INTERVAL > 0) {
            state.refreshTimer = setInterval(loadUserSessions, CONFIG.REFRESH_INTERVAL);
        }

        debugLog('History sidebar initialized');
    }

    // Setup sidebar toggle functionality
    function setupSidebarToggle() {
        const sidebar = document.getElementById('history-sidebar');
        const toggleBtn = document.getElementById('sidebar-toggle');
        const toggleIcon = document.getElementById('toggle-icon');

        if (!sidebar || !toggleBtn) {
            debugLog('Sidebar elements not found');
            return;
        }

        toggleBtn.addEventListener('click', function () {
            sidebar.classList.toggle('collapsed');
            const isCollapsed = sidebar.classList.contains('collapsed');

            if (toggleIcon) {
                toggleIcon.className = isCollapsed ? 'fas fa-chevron-right' : 'fas fa-chevron-left';
            }

            debugLog('Sidebar toggled', isCollapsed ? 'collapsed' : 'expanded');
        });
    }

    // Setup clear history button
    function setupClearHistoryButton() {
        const clearBtn = document.getElementById('clear-history-btn');
        if (!clearBtn) return;

        clearBtn.addEventListener('click', async function () {
            if (!confirm('Are you sure you want to clear all chat history? This action cannot be undone.')) {
                return;
            }

            try {
                showLoading(true);

                const response = await fetch(CONFIG.ENDPOINTS.CLEAR_ALL, {
                    method: 'DELETE',
                    credentials: 'include',
                    headers: {
                        'Accept': 'application/json'
                    }
                });

                const data = await response.json();

                if (data.success) {
                    state.sessions = [];
                    state.currentSessionId = null;
                    renderSessionList();

                    // Clear the main UI
                    if (window.clearChat) window.clearChat();
                    if (window.resetPDFViewer) window.resetPDFViewer();
                    if (window.resetUI) window.resetUI();

                    showNotification('All history cleared successfully', 'success');
                } else {
                    showNotification('Failed to clear history', 'error');
                }
            } catch (error) {
                debugLog('Error clearing history', error);
                showNotification('Error clearing history', 'error');
            } finally {
                showLoading(false);
            }
        });
    }

    // Load user sessions from backend
    async function loadUserSessions() {
        debugLog('Loading user sessions');

        try {
            const response = await fetch(CONFIG.ENDPOINTS.USER_SESSIONS, {
                method: 'GET',
                credentials: 'include',
                headers: {
                    'Accept': 'application/json',
                    'Content-Type': 'application/json'
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            debugLog('Received sessions data', data);

            if (data.success) {
                state.sessions = data.sessions || [];
                state.currentSessionId = data.current_session || state.currentSessionId;
                renderSessionList();
            } else {
                debugLog('No sessions found');
                showEmptyState();
            }
        } catch (error) {
            debugLog('Error loading sessions', error);
            console.error('Error loading sessions:', error);
            showEmptyState();
        }
    }

    // Render session list
    function renderSessionList() {
        debugLog('Rendering session list', `${state.sessions.length} sessions`);

        const sessionList = document.getElementById('session-list');
        if (!sessionList) {
            debugLog('Session list element not found');
            return;
        }

        if (state.sessions.length === 0) {
            showEmptyState();
            return;
        }

        sessionList.innerHTML = '';

        // Group sessions by date
        const groupedSessions = groupSessionsByDate(state.sessions);

        Object.keys(groupedSessions).forEach(dateGroup => {
            // Add date header
            const dateHeader = document.createElement('div');
            dateHeader.className = 'session-date-header';
            dateHeader.style.cssText = 'color: rgba(255, 255, 255, 0.7); font-size: 0.8rem; padding: 0.5rem; margin-top: 0.5rem; font-weight: 600;';
            dateHeader.textContent = formatDateHeader(dateGroup);
            sessionList.appendChild(dateHeader);

            // Add sessions for this date
            groupedSessions[dateGroup].forEach(session => {
                const sessionElement = createSessionElement(session);
                sessionList.appendChild(sessionElement);
            });
        });

        // Update active session highlighting
        if (state.currentSessionId) {
            updateActiveSession(state.currentSessionId);
        }
    }

    // Create session element
    function createSessionElement(session) {
        const div = document.createElement('div');
        div.className = 'session-item';
        div.dataset.sessionId = session.id;

        if (session.id === state.currentSessionId) {
            div.classList.add('active');
        }

        const sessionTime = new Date(session.updated_at || session.created_at);
        const timeStr = sessionTime.toLocaleTimeString('en-US', {
            hour: '2-digit',
            minute: '2-digit'
        });

        const sessionName = session.name || session.session_name || 'Untitled Session';
        const pdfFilename = session.pdf_filename || '';

        div.innerHTML = `
            <div class="session-name">
                <i class="fas fa-file-pdf"></i>
                <span title="${escapeHtml(sessionName)}">${escapeHtml(truncateText(sessionName, 25))}</span>
            </div>
            <div class="session-meta">
                <span><i class="fas fa-clock"></i> ${timeStr}</span>
                ${pdfFilename ? `<span><i class="fas fa-paperclip"></i> ${escapeHtml(truncateText(pdfFilename, 20))}</span>` : ''}
            </div>
            <div class="session-actions">
                <button class="session-action-btn rename" title="Rename">
                    <i class="fas fa-edit"></i>
                </button>
                <button class="session-action-btn delete" title="Delete">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        `;

        // Add click event to load session
        div.addEventListener('click', function (e) {
            if (!e.target.closest('.session-actions')) {
                loadSession(session.id);
            }
        });

        // Add action button events
        const renameBtn = div.querySelector('.rename');
        const deleteBtn = div.querySelector('.delete');

        if (renameBtn) {
            renameBtn.addEventListener('click', function (e) {
                e.stopPropagation();
                renameSession(session.id, sessionName);
            });
        }

        if (deleteBtn) {
            deleteBtn.addEventListener('click', function (e) {
                e.stopPropagation();
                deleteSession(session.id);
            });
        }

        return div;
    }

    // Load a specific session
    async function loadSession(sessionId) {
        if (state.isLoading || sessionId === state.currentSessionId) {
            debugLog('Session already loading or current', sessionId);
            return;
        }

        debugLog('Loading session', sessionId);
        state.isLoading = true;
        showSessionLoading(true);

        try {
            // First, load the session on the backend
            const loadResponse = await fetch(`${CONFIG.ENDPOINTS.LOAD_SESSION}/${sessionId}`, {
                method: 'POST',
                credentials: 'include',
                headers: {
                    'Accept': 'application/json',
                    'Content-Type': 'application/json'
                }
            });

            if (!loadResponse.ok) {
                throw new Error('Failed to load session');
            }

            const loadData = await loadResponse.json();
            debugLog('Session loaded', loadData);

            if (!loadData.success) {
                throw new Error(loadData.message || 'Failed to load session');
            }

            // Then, get the messages for this session
            const messagesResponse = await fetch(CONFIG.ENDPOINTS.SESSION_MESSAGES.replace('{id}', sessionId), {
                method: 'GET',
                credentials: 'include',
                headers: {
                    'Accept': 'application/json'
                }
            });

            if (!messagesResponse.ok) {
                throw new Error('Failed to load messages');
            }

            const messagesData = await messagesResponse.json();
            debugLog('Messages loaded', messagesData);

            if (messagesData.success) {
                state.currentSessionId = sessionId;

                // Clear current UI
                if (window.clearChat) window.clearChat();

                // Load PDF if available
                if (messagesData.pdf_filename && messagesData.pdf_path) {
                    await loadSessionPDF(sessionId, messagesData.pdf_filename);
                }

                // Restore chat messages
                restoreChatMessages(messagesData.messages);

                // Update UI elements
                updateSessionUI(sessionId, messagesData.pdf_filename);
                updateActiveSession(sessionId);

                // Enable chat interface
                enableChatInterface();

                // Update session in browser storage
                if (window.sessionStorage) {
                    window.sessionStorage.setItem('session_id', sessionId);
                }

                showNotification('Session loaded successfully', 'success');
            }
        } catch (error) {
            debugLog('Error loading session', error);
            console.error('Error loading session:', error);
            showNotification('Failed to load session', 'error');
        } finally {
            state.isLoading = false;
            showSessionLoading(false);
        }
    }

    // Load session PDF
    async function loadSessionPDF(sessionId, filename) {
        debugLog('Loading PDF for session', { sessionId, filename });

        try {
            const response = await fetch(CONFIG.ENDPOINTS.SESSION_PDF.replace('{id}', sessionId), {
                method: 'GET',
                credentials: 'include'
            });

            if (!response.ok) {
                throw new Error('Failed to load PDF');
            }

            const blob = await response.blob();
            const file = new File([blob], filename, { type: 'application/pdf' });

            // Use the existing PDF rendering function from dashboard.js
            if (window.renderPDF) {
                await window.renderPDF(file);
            }

            // Update PDF viewer UI
            const pdfViewer = document.getElementById('pdf-viewer');
            if (pdfViewer) {
                pdfViewer.style.display = 'flex';
            }

            const pdfFilename = document.getElementById('pdf-filename');
            if (pdfFilename) {
                pdfFilename.textContent = filename;
            }

            // Update upload status
            const uploadStatus = document.getElementById('upload-status');
            if (uploadStatus) {
                uploadStatus.innerHTML = `
                    <i class="fas fa-check-circle" style="color: var(--success-color);"></i>
                    <span style="color: var(--success-color); font-weight: 600;">Document loaded: ${filename}</span>
                `;
            }

            // Update upload button
            const uploadBtn = document.getElementById('upload-compact-btn');
            if (uploadBtn) {
                uploadBtn.innerHTML = '<i class="fas fa-sync-alt"></i><span>Change PDF</span>';
                uploadBtn.disabled = false;
            }

            debugLog('PDF loaded successfully');
        } catch (error) {
            debugLog('Error loading PDF', error);
            console.error('Error loading PDF:', error);
        }
    }

    // Restore chat messages
    function restoreChatMessages(messages) {
        if (!messages || messages.length === 0) {
            debugLog('No messages to restore');
            return;
        }

        debugLog('Restoring messages', `${messages.length} messages`);

        const messagesContainer = document.getElementById('messages-container');
        if (!messagesContainer) return;

        // Clear existing messages
        messagesContainer.innerHTML = '';

        // Add each message
        messages.forEach(message => {
            if (message.sender !== 'system') {
                if (window.addMessage) {
                    window.addMessage(message.sender, message.content, false);
                }
            }
        });

        // Scroll to bottom
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    // Delete session
    async function deleteSession(sessionId) {
        if (!confirm('Are you sure you want to delete this session? This action cannot be undone.')) {
            return;
        }

        debugLog('Deleting session', sessionId);

        try {
            const response = await fetch(`${CONFIG.ENDPOINTS.DELETE_SESSION}/${sessionId}`, {
                method: 'DELETE',
                credentials: 'include',
                headers: {
                    'Accept': 'application/json'
                }
            });

            const data = await response.json();

            if (data.success) {
                // Remove from local state
                state.sessions = state.sessions.filter(s => s.id !== sessionId);

                // If this was the current session, clear everything
                if (sessionId === state.currentSessionId) {
                    state.currentSessionId = null;
                    if (window.clearChat) window.clearChat();
                    if (window.resetPDFViewer) window.resetPDFViewer();
                    if (window.resetUI) window.resetUI();
                }

                // Re-render list
                renderSessionList();
                showNotification('Session deleted successfully', 'success');
            } else {
                showNotification('Failed to delete session', 'error');
            }
        } catch (error) {
            debugLog('Error deleting session', error);
            console.error('Error deleting session:', error);
            showNotification('Error deleting session', 'error');
        }
    }

    // Rename session
    async function renameSession(sessionId, currentName) {
        const newName = prompt('Enter new name for session:', currentName);
        if (!newName || newName === currentName) return;

        debugLog('Renaming session', { sessionId, newName });

        try {
            const response = await fetch(`${CONFIG.ENDPOINTS.RENAME_SESSION}/${sessionId}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                body: JSON.stringify({ name: newName }),
                credentials: 'include'
            });

            const data = await response.json();

            if (data.success) {
                // Update in local state
                const session = state.sessions.find(s => s.id === sessionId);
                if (session) {
                    session.name = newName;
                    session.session_name = newName;
                }

                // Re-render list
                renderSessionList();
                showNotification('Session renamed successfully', 'success');
            } else {
                showNotification('Failed to rename session', 'error');
            }
        } catch (error) {
            debugLog('Error renaming session', error);
            console.error('Error renaming session:', error);
            showNotification('Error renaming session', 'error');
        }
    }

    // Helper Functions

    function groupSessionsByDate(sessions) {
        const grouped = {};
        const today = new Date().toDateString();
        const yesterday = new Date(Date.now() - 86400000).toDateString();

        sessions.forEach(session => {
            const date = new Date(session.updated_at || session.created_at).toDateString();
            let groupKey;

            if (date === today) {
                groupKey = 'Today';
            } else if (date === yesterday) {
                groupKey = 'Yesterday';
            } else {
                groupKey = date;
            }

            if (!grouped[groupKey]) {
                grouped[groupKey] = [];
            }
            grouped[groupKey].push(session);
        });

        return grouped;
    }

    function formatDateHeader(dateStr) {
        if (dateStr === 'Today' || dateStr === 'Yesterday') {
            return dateStr;
        }
        return new Date(dateStr).toLocaleDateString('en-US', {
            weekday: 'long',
            year: 'numeric',
            month: 'short',
            day: 'numeric'
        });
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text || '';
        return div.innerHTML;
    }

    function truncateText(text, maxLength) {
        if (!text) return '';
        if (text.length <= maxLength) return text;
        return text.substring(0, maxLength - 3) + '...';
    }

    function showEmptyState() {
        const sessionList = document.getElementById('session-list');
        if (!sessionList) return;

        sessionList.innerHTML = `
            <div class="empty-history">
                <i class="fas fa-folder-open"></i>
                <p>No chat history yet.<br>Upload a document to begin.</p>
            </div>
        `;
    }

    function showSessionLoading(show) {
        const loader = document.getElementById('session-loading');
        if (loader) {
            loader.classList.toggle('active', show);
        }
    }

    function showLoading(show) {
        // You can implement a general loading indicator here if needed
        debugLog('Loading state', show);
    }

    function updateActiveSession(sessionId) {
        // Remove active class from all sessions
        document.querySelectorAll('.session-item').forEach(item => {
            item.classList.remove('active');
        });

        // Add active class to selected session
        const activeItem = document.querySelector(`[data-session-id="${sessionId}"]`);
        if (activeItem) {
            activeItem.classList.add('active');
        }
    }

    function updateSessionUI(sessionId, pdfFilename) {
        const sessionInfo = document.getElementById('session-info');
        if (sessionInfo) {
            const session = state.sessions.find(s => s.id === sessionId);
            if (session) {
                sessionInfo.textContent = `Session: ${truncateText(session.name || session.session_name, 30)}`;
            }
        }

        const pdfFilenameDisplay = document.getElementById('pdf-filename');
        if (pdfFilenameDisplay && pdfFilename) {
            pdfFilenameDisplay.textContent = pdfFilename;
        }
    }

    function enableChatInterface() {
        const messageInput = document.getElementById('message-input');
        const sendButton = document.getElementById('send-button');

        if (messageInput) messageInput.disabled = false;
        if (sendButton) sendButton.disabled = false;

        // Show new session button
        const newSessionBtn = document.getElementById('new-session-btn');
        if (newSessionBtn) {
            newSessionBtn.style.display = 'inline-flex';
        }

        // Mark document as processed
        if (window.documentProcessed !== undefined) {
            window.documentProcessed = true;
        }
    }

    function showNotification(message, type = 'info') {
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;

        const iconMap = {
            'success': 'check-circle',
            'error': 'exclamation-circle',
            'warning': 'exclamation-triangle',
            'info': 'info-circle'
        };

        const colorMap = {
            'success': '#198754',
            'error': '#dc3545',
            'warning': '#ffc107',
            'info': '#0dcaf0'
        };

        notification.style.cssText = `
            position: fixed;
            top: 100px;
            right: 20px;
            padding: 1rem 1.5rem;
            border-radius: 8px;
            background: white;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
            display: flex;
            align-items: center;
            gap: 0.75rem;
            z-index: 10000;
            animation: slideIn 0.3s ease;
            max-width: 400px;
            border-left: 4px solid ${colorMap[type]};
        `;

        notification.innerHTML = `
            <i class="fas fa-${iconMap[type]}" style="color: ${colorMap[type]}; font-size: 1.2rem;"></i>
            <span style="color: #333;">${message}</span>
        `;

        document.body.appendChild(notification);

        // Auto-remove after 3 seconds
        setTimeout(() => {
            notification.style.animation = 'slideOut 0.3s ease';
            notification.style.animationFillMode = 'forwards';
            setTimeout(() => {
                if (notification.parentNode) {
                    document.body.removeChild(notification);
                }
            }, 300);
        }, 3000);
    }

    // Add CSS animations if not already present
    function addAnimationStyles() {
        if (document.getElementById('history-animations')) return;

        const style = document.createElement('style');
        style.id = 'history-animations';
        style.textContent = `
            @keyframes slideIn {
                from {
                    transform: translateX(100%);
                    opacity: 0;
                }
                to {
                    transform: translateX(0);
                    opacity: 1;
                }
            }
            
            @keyframes slideOut {
                from {
                    transform: translateX(0);
                    opacity: 1;
                }
                to {
                    transform: translateX(100%);
                    opacity: 0;
                }
            }
        `;
        document.head.appendChild(style);
    }

    // Initialize when DOM is ready
    function init() {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', initializeHistorySidebar);
        } else {
            initializeHistorySidebar();
        }
        addAnimationStyles();
    }

    // Export functions to global scope for dashboard.js integration
    window.historyManager = {
        loadUserSessions,
        loadSession,
        deleteSession,
        renameSession,
        refreshSessions: loadUserSessions,
        getCurrentSessionId: () => state.currentSessionId
    };

    // Start initialization
    init();

})();

console.log('History.js loaded - Persistent session management ready');