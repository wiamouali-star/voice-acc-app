// Configuration
const API_BASE = '/api';

// Éléments DOM - Version robuste
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
let currentChatArticle = null;
let chatModal = null;

// Vérification des éléments DOM
function initializeDOMElements() {
    console.log('🔍 Initialisation des éléments DOM...');
    
    // Vérifier et créer si nécessaire le conteneur principal
    if (!elements.newsContainer) {
        console.log('❌ news-container non trouvé, création...');
        const container = document.createElement('div');
        container.id = 'news-container';
        const resultsSection = document.querySelector('.results-section');
        if (resultsSection) {
            resultsSection.appendChild(container);
            elements.newsContainer = container;
        }
    }
    
    // Vérifier les autres éléments critiques
    if (!elements.status) {
        console.error('❌ Élément status non trouvé');
    }
    
    if (!elements.loading) {
        console.log('⚠️ Loading indicator non trouvé');
    }
    
    console.log('✅ Éléments DOM initialisés:', {
        newsContainer: !!elements.newsContainer,
        status: !!elements.status,
        loading: !!elements.loading
    });
}

// Gestion du chargement
function showLoading() {
    console.log('🔄 Affichage du chargement...');
    if (elements.loading) {
        elements.loading.style.display = 'block';
    }
    if (elements.newsContainer) {
        elements.newsContainer.innerHTML = '<div class="loading">Chargement des actualités...</div>';
    }
}

function hideLoading() {
    if (elements.loading) {
        elements.loading.style.display = 'none';
    }
}

// Formatage des dates
function formatDate(dateString) {
    try {
        const date = new Date(dateString);
        return date.toLocaleDateString('fr-FR', {
            day: 'numeric',
            month: 'short',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    } catch (e) {
        return 'Date inconnue';
    }
}

// Classification
async function classifyQuery(query) {
    try {
        console.log('🔍 Classification de la requête:', query);
        const res = await fetch(`${API_BASE}/classify`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query })
        });
        
        if (!res.ok) {
            throw new Error(`Erreur HTTP: ${res.status}`);
        }
        
        const data = await res.json();
        console.log('✅ Résultat classification:', data);
        return data;
    } catch (error) {
        console.error('❌ Erreur classification:', error);
        return null;
    }
}

// Reconnaissance vocale
function initializeVoiceRecognition() {
    if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
        console.warn('❌ Reconnaissance vocale non supportée');
        if (elements.micButton) elements.micButton.style.display = 'none';
        if (elements.status) elements.status.textContent = 'Reconnaissance vocale non supportée';
        return;
    }

    recognition = new (window.webkitSpeechRecognition || window.SpeechRecognition)();
    recognition.lang = 'fr-FR';
    recognition.continuous = false;
    recognition.interimResults = false;

    recognition.onstart = () => {
        console.log('🎤 Reconnaissance vocale démarrée');
        if (elements.status) elements.status.textContent = '🎤 Écoute en cours...';
        if (elements.micButton) elements.micButton.classList.add('listening');
    };

    recognition.onend = () => {
        console.log('🎤 Reconnaissance vocale arrêtée');
        if (elements.status) elements.status.textContent = 'Cliquez sur le microphone pour parler';
        if (elements.micButton) elements.micButton.classList.remove('listening');
        isListening = false;
    };

    recognition.onresult = async (event) => {
        try {
            const transcript = event.results[0][0].transcript.trim();
            console.log('🗣️ Transcription:', transcript);
            
            if (elements.searchInput) elements.searchInput.value = transcript;
            if (elements.status) elements.status.textContent = `📝 Transcription: "${transcript}"`;

            // Classification et recherche
            const classification = await classifyQuery(transcript);
            
            if (classification && classification.category && classification.category !== 'autre') {
                console.log('🎯 Recherche par catégorie:', classification.category);
                if (elements.status) {
                    elements.status.textContent = `🎯 Catégorie: ${classification.category}`;
                }
                await loadNews(classification.category, true);
            } else {
                console.log('🔍 Recherche par texte:', transcript);
                await loadNews(transcript, true);
            }
        } catch (error) {
            console.error('❌ Erreur traitement vocal:', error);
            displayError('Erreur lors du traitement vocal');
        }
    };

    recognition.onerror = (event) => {
        console.error('❌ Erreur reconnaissance:', event.error);
        if (elements.status) elements.status.textContent = '❌ Erreur de reconnaissance';
        if (elements.micButton) elements.micButton.classList.remove('listening');
        isListening = false;
    };

    // Gestionnaire du microphone
    if (elements.micButton) {
        elements.micButton.addEventListener('click', async () => {
            try {
                // Test de permission microphone
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                stream.getTracks().forEach(track => track.stop());

                if (isListening) {
                    recognition.stop();
                    isListening = false;
                    if (elements.status) elements.status.textContent = 'Reconnaissance arrêtée';
                } else {
                    recognition.start();
                    isListening = true;
                    console.log('🎤 Démarrage reconnaissance...');
                }
            } catch (error) {
                console.error('❌ Permission microphone refusée:', error);
                if (elements.status) elements.status.textContent = '🎤 Autorisez l\'accès au microphone';
            }
        });
    }
}

// Recherche manuelle
function initializeSearchHandlers() {
    if (elements.searchButton) {
        elements.searchButton.addEventListener('click', handleSearch);
    }
    
    if (elements.searchInput) {
        elements.searchInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                handleSearch();
            }
        });
    }
}

async function handleSearch() {
    const query = elements.searchInput ? elements.searchInput.value.trim() : '';
    if (!query) {
        if (elements.status) elements.status.textContent = '❌ Veuillez saisir une recherche';
        return;
    }

    try {
        console.log('🔍 Lancement recherche:', query);
        const classification = await classifyQuery(query);
        
        if (classification && classification.category && classification.category !== 'autre') {
            if (elements.status) {
                elements.status.textContent = `🎯 Recherche par catégorie: ${classification.category}`;
            }
            await loadNews(classification.category, true);
        } else {
            await loadNews(query, true);
        }
    } catch (error) {
        console.error('❌ Erreur recherche:', error);
        displayError('Erreur lors de la recherche');
    }
}

// FONCTION PRINCIPALE - loadNews
async function loadNews(topic = '', isSearch = false) {
    console.log('📰 Chargement des actualités, topic:', topic, 'isSearch:', isSearch);
    
    try {
        showLoading();
        
        let url = `${API_BASE}/news`;
        const params = new URLSearchParams();
        
        if (topic) {
            params.append('topic', topic);
            if (isSearch) params.append('logged', '1');
        }
        
        // Ajouter un timestamp pour éviter le cache
        params.append('_t', Date.now());
        
        if (params.toString()) {
            url += `?${params.toString()}`;
        }
        
        console.log('🌐 Fetch URL:', url);
        
        const response = await fetch(url);
        
        if (!response.ok) {
            throw new Error(`Erreur HTTP ${response.status}: ${response.statusText}`);
        }
        
        const articles = await response.json();
        console.log('✅ Réponse API brute:', articles);
        
        // VÉRIFICATION APPROFONDIE
        if (!articles) {
            throw new Error('Aucune donnée reçue du serveur');
        }
        
        if (!Array.isArray(articles)) {
            console.error('❌ Format invalide, reçu:', typeof articles, articles);
            throw new Error('Format de données invalide - tableau attendu');
        }
        
        if (articles.length === 0) {
            displayNoResults(topic);
            return;
        }
        
        // AFFICHAGE
        displayArticles(articles, topic);
        
    } catch (error) {
        console.error('❌ Erreur loadNews:', error);
        displayError(`Erreur de chargement: ${error.message}`);
    } finally {
        hideLoading();
    }
}

// FONCTION D'AFFICHAGE DES ARTICLES
function displayArticles(articles, topic) {
    console.log('🖼️ Affichage des articles:', articles);
    
    if (!articles || articles.length === 0) {
        displayNoResults(topic);
        return;
    }

    // Mettre à jour les statistiques
    updateStats(articles, topic);

    const articlesHTML = articles.map((article, index) => {
        console.log(`📄 Article ${index}:`, article);
        
        // Validation robuste des données
        const title = article.title || `Actualité ${index + 1}`;
        const summary = article.summary || article.description || 'Aucun résumé disponible';
        const source = article.source || 'Source inconnue';
        const link = article.link || article.url || '#';
        const published = article.published ? formatDate(article.published) : 
                         article.pubDate ? formatDate(article.pubDate) : 
                         article.date ? formatDate(article.date) : '';
        
        // Utiliser le format CARTE avec bouton de chat
        return `
            <div class="article-card fade-in">
                <div class="article-image">
                    ${getArticleIcon(source)}
                </div>
                <div class="article-content">
                    <div class="article-header">
                        <h3 class="article-title">${title}</h3>
                        <span class="article-source">${source}</span>
                    </div>
                    <p class="article-summary">${summary}</p>
                    <div class="article-footer">
                        ${published ? `<span class="article-date">${published}</span>` : ''}
                        ${link !== '#' ? `
                            <a href="${link}" target="_blank" rel="noopener" class="article-link">
                                Lire l'article →
                            </a>
                        ` : ''}
                    </div>
                    <div class="article-actions">
                        <button
                            class="chat-btn"
                            onclick="openChatForArticle(${JSON.stringify(article).replace(/"/g, '&quot;')})">
                            💬 Discuter avec le bot
                        </button>
                    </div>
                </div>
            </div>
        `;
    }).join('');
    
    console.log('📊 HTML généré avec cartes');

    if (elements.newsContainer) {
        elements.newsContainer.innerHTML = articlesHTML;
        console.log('✅ Articles affichés en format carte!');
        
        // Mettre à jour le titre des résultats
        updateResultsTitle(topic, articles.length);
    } else {
        console.error('❌ Conteneur news-container introuvable!');
        displayError('Erreur d\'affichage - conteneur non trouvé');
    }
}

// Fonction pour obtenir une icône basée sur la source
function getArticleIcon(source) {
    const iconMap = {
        'Le Monde': '📰',
        'France 24': '🇫🇷',
        'BBC News': '🇬🇧',
        '20 Minutes': '⏱️',
        'Test Sport': '🏆',
        'Test Politique': '🏛️',
        'Test Technologie': '💻'
    };
    return iconMap[source] || '📄';
}

// Mettre à jour le titre des résultats
function updateResultsTitle(topic, count) {
    const resultsTitle = document.getElementById('resultsTitle');
    if (resultsTitle) {
        if (topic) {
            resultsTitle.innerHTML = `🔍 ${count} résultat(s) pour "${topic}"`;
        } else {
            resultsTitle.innerHTML = '📰 Actualités du jour';
        }
    }
}

// Mettre à jour les statistiques
function updateStats(articles, topic) {
    const statsSection = document.getElementById('statsSection');
    const articlesCount = document.getElementById('articlesCount');
    const sourcesCount = document.getElementById('sourcesCount');
    const categoryName = document.getElementById('categoryName');
    
    if (statsSection && articlesCount && sourcesCount && categoryName) {
        // Compter les sources uniques
        const uniqueSources = [...new Set(articles.map(article => article.source))];
        
        articlesCount.textContent = articles.length;
        sourcesCount.textContent = uniqueSources.length;
        categoryName.textContent = topic || 'Général';
        
        // Afficher la section stats
        statsSection.style.display = 'block';
        statsSection.classList.add('slide-down');
    }
}

function displayNoResults(topic) {
    console.log('📭 Aucun résultat pour:', topic);
    
    const message = topic ? 
        `Aucun article trouvé pour "${topic}". Essayez avec d'autres termes.` :
        'Aucun article disponible pour le moment.';
    
    if (elements.newsContainer) {
        elements.newsContainer.innerHTML = `
            <div class="no-results">
                <h3>🔍 Aucun résultat</h3>
                <p>${message}</p>
            </div>
        `;
    }
    
    if (elements.status) {
        elements.status.textContent = message;
    }
}

function displayError(message) {
    console.error('🚨 Affichage erreur:', message);
    
    if (elements.newsContainer) {
        elements.newsContainer.innerHTML = `
            <div class="error-message">
                <h3>❌ Erreur</h3>
                <p>${message}</p>
                <button onclick="loadNews()" class="retry-btn">Réessayer</button>
            </div>
        `;
    }
    
    if (elements.status) {
        elements.status.textContent = message;
    }
}

// Gestion des catégories
function initializeCategoryButtons() {
    const categoryButtons = document.querySelectorAll('.topic-tag');
    categoryButtons.forEach(button => {
        button.addEventListener('click', async () => {
            // Retirer la classe active de tous les boutons
            categoryButtons.forEach(btn => btn.classList.remove('active'));
            // Ajouter la classe active au bouton cliqué
            button.classList.add('active');
            
            const category = button.dataset.category;
            await loadNews(category, true);
        });
    });
}

// Gestion des vues
function initializeViewButtons() {
    const viewButtons = document.querySelectorAll('.view-btn');
    const newsContainer = document.getElementById('news-container');
    
    viewButtons.forEach(button => {
        button.addEventListener('click', () => {
            viewButtons.forEach(btn => btn.classList.remove('active'));
            button.classList.add('active');
            
            const viewType = button.dataset.view;
            newsContainer.className = `news-container ${viewType}-view`;
        });
    });
}

// Fonctionnalités améliorées
function initializeEnhancedFeatures() {
    console.log('🎨 Initialisation des fonctionnalités améliorées...');
    
    // Gestion des sujets rapides
    const topicTags = document.querySelectorAll('.topic-tag');
    topicTags.forEach(tag => {
        tag.addEventListener('click', () => {
            const topic = tag.getAttribute('data-topic');
            if (elements.searchInput) {
                elements.searchInput.value = topic;
            }
            loadNews(topic, true);
        });
    });
    
    // Gestion du tri
    const sortNewest = document.getElementById('sortNewest');
    const sortOldest = document.getElementById('sortOldest');
    
    if (sortNewest) {
        sortNewest.addEventListener('click', () => sortArticles('newest'));
    }
    if (sortOldest) {
        sortOldest.addEventListener('click', () => sortArticles('oldest'));
    }
    
    // Mise à jour de l'heure dans le footer
    updateFooterTime();
}

// Fonction de tri des articles
function sortArticles(order) {
    const articlesContainer = elements.newsContainer;
    const articles = Array.from(articlesContainer.querySelectorAll('.article-card'));
    
    articles.sort((a, b) => {
        const dateA = getArticleDate(a);
        const dateB = getArticleDate(b);
        
        if (order === 'newest') {
            return dateB - dateA;
        } else {
            return dateA - dateB;
        }
    });
    
    // Réorganiser les articles
    articles.forEach(article => articlesContainer.appendChild(article));
    
    // Mettre à jour les boutons de tri
    updateSortButtons(order);
}

function getArticleDate(articleElement) {
    const dateElement = articleElement.querySelector('.article-date');
    return dateElement ? new Date(dateElement.textContent) : new Date();
}

function updateSortButtons(activeOrder) {
    const buttons = document.querySelectorAll('.filter-btn');
    buttons.forEach(btn => btn.classList.remove('active'));
    
    const activeButton = document.getElementById(activeOrder === 'newest' ? 'sortNewest' : 'sortOldest');
    if (activeButton) {
        activeButton.classList.add('active');
    }
}

function updateFooterTime() {
    const lastUpdate = document.getElementById('lastUpdate');
    if (lastUpdate) {
        lastUpdate.textContent = new Date().toLocaleDateString('fr-FR', {
            day: 'numeric',
            month: 'long',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    }
}

// ============================================
// SYSTÈME DE CHAT SIMPLIFIÉ
// ============================================

// Fonction pour ouvrir le chat
async function openChatForArticle(article) {
    console.log('💬 Ouverture du chat simplifié');

    try {
        currentChatArticle = article;
        console.log('📰 Article sélectionné:', currentChatArticle);

        // Créer ou réutiliser le modal de chat
        if (!chatModal) {
            createChatModal();
        }
        
        // Afficher le modal et l'overlay
        chatModal.style.display = 'flex';
        const overlay = document.getElementById('chat-overlay');
        if (overlay) {
            overlay.style.display = 'block';
        }
        
        // Initialiser le chat avec un message de bienvenue
        const messagesContainer = document.getElementById('chat-messages');
        messagesContainer.innerHTML = `
            <div class="message bot-message">
                <strong>🤖 Assistant:</strong> Je peux répondre à vos questions sur cet article : "<em>${article.title}</em>"
            </div>
        `;

    } catch (error) {
        console.error('❌ Erreur ouverture chat:', error);
        alert('Erreur lors de l\'ouverture du chat');
    }
}

// Créer le modal de chat
function createChatModal() {
    chatModal = document.createElement('div');
    chatModal.id = 'chat-modal';
    chatModal.style.cssText = `
        position: fixed;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        width: 90%;
        max-width: 500px;
        height: 70vh;
        background: white;
        border-radius: 10px;
        box-shadow: 0 5px 25px rgba(0,0,0,0.3);
        z-index: 1000;
        display: none;
        flex-direction: column;
    `;
    
    chatModal.innerHTML = `
        <div style="padding: 15px; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; align-items: center; background: #f8f9fa; border-radius: 10px 10px 0 0;">
            <h3 style="margin: 0; font-size: 16px;">💬 Discussion sur l'article</h3>
            <button id="chat-close" style="background: none; border: none; font-size: 20px; cursor: pointer; color: #666;">×</button>
        </div>
        
        <div id="chat-messages" style="flex: 1; overflow-y: auto; padding: 15px; background: #fafafa;">
            <!-- Messages apparaîtront ici -->
        </div>
        
        <div style="padding: 15px; border-top: 1px solid #eee; background: white; border-radius: 0 0 10px 10px;">
            <div style="display: flex; gap: 10px;">
                <input 
                    type="text" 
                    id="chat-input" 
                    placeholder="Posez une question sur cet article..." 
                    style="flex: 1; padding: 10px; border: 1px solid #ddd; border-radius: 5px; font-size: 14px;"
                >
                <button 
                    id="chat-send" 
                    style="padding: 10px 15px; background: #0078d4; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 14px;"
                >
                    Envoyer
                </button>
            </div>
        </div>
    `;
    
    document.body.appendChild(chatModal);
    
    // Créer l'overlay
    const overlay = document.createElement('div');
    overlay.id = 'chat-overlay';
    overlay.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0,0,0,0.5);
        z-index: 999;
        display: none;
    `;
    document.body.appendChild(overlay);
    
    // Gestionnaires d'événements
    document.getElementById('chat-close').addEventListener('click', closeChat);
    document.getElementById('chat-send').addEventListener('click', sendChatMessage);
    overlay.addEventListener('click', closeChat);
    
    // Entrée clavier
    document.getElementById('chat-input').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            sendChatMessage();
        }
    });
}

// Fermer le chat
function closeChat() {
    if (chatModal) {
        chatModal.style.display = 'none';
    }
    const overlay = document.getElementById('chat-overlay');
    if (overlay) {
        overlay.style.display = 'none';
    }
    currentChatArticle = null;
}

// Envoyer un message
async function sendChatMessage() {
    if (!currentChatArticle) {
        console.error('❌ Aucun article sélectionné');
        return;
    }
    
    const input = document.getElementById('chat-input');
    const message = input.value.trim();
    
    if (!message) {
        return;
    }
    
    // Ajouter le message de l'utilisateur
    addMessageToChat('user', message);
    input.value = '';
    input.disabled = true;
    
    try {
        console.log('📤 Envoi message au backend Flask...');
        
        // APPEL DIRECT au backend Flask
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                message: message,
                article: {
                    title: currentChatArticle.title,
                    summary: currentChatArticle.summary,
                    url: currentChatArticle.link || currentChatArticle.url
                }
            })
        });
        
        if (!response.ok) {
            throw new Error(`Erreur HTTP: ${response.status}`);
        }
        
        const data = await response.json();
        console.log('✅ Réponse reçue:', data);
        
        if (data.reply) {
            addMessageToChat('bot', data.reply);
        } else if (data.error) {
            addMessageToChat('bot', `❌ Erreur: ${data.message || data.error}`);
        } else {
            addMessageToChat('bot', '❌ Réponse inattendue du serveur');
        }
        
    } catch (error) {
        console.error('❌ Erreur envoi message:', error);
        addMessageToChat('bot', '❌ Erreur de connexion au serveur');
    } finally {
        input.disabled = false;
        input.focus();
    }
}

// Ajouter un message au chat
function addMessageToChat(sender, text) {
    const container = document.getElementById('chat-messages');
    if (!container) return;
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${sender}-message`;
    messageDiv.style.cssText = `
        margin: 10px 0;
        padding: 10px 15px;
        border-radius: 15px;
        max-width: 80%;
        line-height: 1.4;
        animation: fadeIn 0.3s ease-in;
        ${sender === 'user' 
            ? 'background: #0078d4; color: white; margin-left: auto; text-align: right;' 
            : 'background: #f0f0f0; color: #333; margin-right: auto; border: 1px solid #e1e5e9;'
        }
    `;
    
    messageDiv.innerHTML = `
        <strong>${sender === 'user' ? '👤 Vous' : '🤖 Assistant'}:</strong><br>
        ${text.replace(/\n/g, '<br>')}
    `;
    
    container.appendChild(messageDiv);
    container.scrollTop = container.scrollHeight;
}

// Initialisation du modal de chat
function initializeChatModal() {
    // S'assurer que le modal est créé au chargement
    if (!chatModal) {
        createChatModal();
    }
}

// ============================================
// INITIALISATION PRINCIPALE
// ============================================

async function initializeApp() {
    console.log('🚀 Initialisation de l\'application...');
    
    // Initialisation DOM
    initializeDOMElements();
    
    // Initialisation reconnaissance vocale
    initializeVoiceRecognition();
    
    // Initialisation recherche
    initializeSearchHandlers();
    
    // Initialisation des catégories
    initializeCategoryButtons();
    
    // Initialisation des vues
    initializeViewButtons();

    // Initialisation fonctionnalités améliorées
    initializeEnhancedFeatures();
    
    // Initialisation du chat
    initializeChatModal();
    
    // Chargement initial
    try {
        await loadNews();
        console.log('🎉 Application initialisée avec succès!');
    } catch (error) {
        console.error('❌ Erreur initialisation:', error);
        displayError('Erreur lors du chargement initial');
    }
}

// Démarrage de l'application
document.addEventListener('DOMContentLoaded', initializeApp);

// Export des fonctions globales pour l'HTML
window.openChatForArticle = openChatForArticle;
window.loadNews = loadNews;
window.closeChat = closeChat;
window.sendChatMessage = sendChatMessage;
