// Configuration
const API_BASE = '/api';

// Éléments DOM
const elements = {
    micButton: document.getElementById('micButton'),
    status: document.getElementById('status'),
    searchInput: document.getElementById('searchInput'),
    searchButton: document.getElementById('searchButton'),
    newsContainer: document.getElementById('news-container'),
    loading: document.getElementById('loading')
};

// État de l'application
let isListening = false;
let recognition = null;

// Initialisation
document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 Initialisation de l\'application...');
    initializeVoiceRecognition();
    loadNews(); // Charger les actualités au démarrage
});

function initializeVoiceRecognition() {
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
        recognition = new (window.webkitSpeechRecognition || window.SpeechRecognition)();
        recognition.lang = 'fr-FR';
        recognition.continuous = false;
        recognition.interimResults = false;

        recognition.onstart = () => {
            elements.status.textContent = 'Écoute en cours...';
            elements.micButton.classList.add('listening');
        };

        recognition.onend = () => {
            elements.status.textContent = 'Cliquez sur le microphone pour commencer';
            elements.micButton.classList.remove('listening');
        };

        recognition.onresult = (event) => {
            const transcript = event.results[0][0].transcript.trim();
            // Supprimer le point final s'il existe
            const cleanTranscript = transcript.endsWith('.') ? transcript.slice(0, -1) : transcript;
            
            console.log('Transcription:', cleanTranscript);
            elements.searchInput.value = cleanTranscript;
            elements.status.textContent = `Vous avez dit: ${cleanTranscript}`;
            loadNews(cleanTranscript);
        };

        recognition.onerror = (event) => {
            console.error('Erreur de reconnaissance:', event.error);
            elements.status.textContent = `Erreur: ${event.error}`;
            elements.micButton.classList.remove('listening');
        };

        // Gestionnaire du bouton microphone
        elements.micButton.addEventListener('click', async () => {
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                stream.getTracks().forEach(track => track.stop());
                recognition.start();
            } catch (error) {
                console.error('Erreur d\'accès au microphone:', error);
                elements.status.textContent = 'Veuillez autoriser l\'accès au microphone';
            }
        });
    } else {
        elements.micButton.style.display = 'none';
        elements.status.textContent = 'La reconnaissance vocale n\'est pas supportée par votre navigateur';
    }
}

async function loadNews(topic = '') {
    try {
        showLoading();
        
        let url = `${API_BASE}/news`;
        if (topic) {
            url += `?topic=${encodeURIComponent(topic)}`;
        }

        console.log('Chargement des actualités:', url);
        const response = await fetch(url);
        
        if (!response.ok) {
            throw new Error(`Erreur HTTP: ${response.status}`);
        }

        const articles = await response.json();
        console.log('Articles reçus:', articles);
        displayArticles(articles);

    } catch (error) {
        console.error('Erreur:', error);
        displayError('Erreur lors du chargement des actualités: ' + error.message);
    } finally {
        hideLoading();
    }
}

function displayArticles(articles) {
    if (!articles || articles.length === 0) {
        displayError('Aucun article trouvé');
        return;
    }

    const articlesHTML = articles.map(article => `
        <div class="article">
            <h3>${article.title || 'Sans titre'}</h3>
            <p class="article-summary">${article.summary || 'Aucun résumé disponible'}</p>
            <div class="article-meta">
                <span class="source">📰 ${article.source || 'Source inconnue'}</span>
                ${article.published ? `<span class="date">📅 ${formatDate(article.published)}</span>` : ''}
                <a href="${article.link}" target="_blank" rel="noopener" class="read-more">Lire l'article →</a>
            </div>
        </div>
    `).join('');

    elements.newsContainer.innerHTML = articlesHTML;
}

function displayError(message) {
    elements.newsContainer.innerHTML = `<div class="error">${message}</div>`;
}

function formatDate(dateString) {
    try {
        const date = new Date(dateString);
        return date.toLocaleDateString('fr-FR', {
            day: 'numeric',
            month: 'long',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    } catch {
        return dateString;
    }
}

function showLoading() {
    if (elements.loading) {
        elements.loading.style.display = 'block';
    }
    elements.newsContainer.innerHTML = '<div class="loading">Chargement des actualités...</div>';
}

function hideLoading() {
    if (elements.loading) {
        elements.loading.style.display = 'none';
    }
}

// Gestionnaires d'événements pour la recherche
if (elements.searchButton) {
    elements.searchButton.addEventListener('click', () => {
        const searchTerm = elements.searchInput.value.trim();
        if (searchTerm) {
            loadNews(searchTerm);
        }
    });
}

if (elements.searchInput) {
    elements.searchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            const searchTerm = elements.searchInput.value.trim();
            if (searchTerm) {
                loadNews(searchTerm);
            }
        }
    });
}