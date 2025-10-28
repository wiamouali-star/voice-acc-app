# ============================================
# ASSISTANT VOCAL INTELLIGENT - Backend Flask
# Version optimisée pour Azure App Service
# ============================================

from flask import Flask, send_from_directory, request, jsonify
from flask_cors import CORS
import feedparser
import os
import re
from datetime import datetime
import logging

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='static', static_url_path='')

# Configuration CORS
CORS(app)

# ============================================
# CONFIGURATION DES SOURCES RSS
# ============================================
NEWS_SOURCES = {
    "Le Monde": "https://www.lemonde.fr/rss/une.xml",
    "France 24": "https://www.france24.com/fr/rss", 
    "BBC News": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "20 Minutes": "https://www.20minutes.fr/rss/une.xml"
}

# Cache simple
news_cache = {
    'data': None,
    'timestamp': None
}

def clean_text(text, max_length=200):
    """Nettoie le texte pour l'affichage"""
    if not text:
        return ""
    
    # Supprimer les balises HTML
    text = re.sub(r'<[^>]+>', '', text)
    
    # Nettoyer les espaces
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Tronquer si nécessaire
    if len(text) > max_length:
        text = text[:max_length] + '...'
    
    return text

def fetch_news():
    """Récupère les actualités depuis les flux RSS"""
    try:
        all_articles = []
        
        for source_name, source_url in NEWS_SOURCES.items():
            try:
                feed = feedparser.parse(source_url)
                
                for entry in feed.entries[:5]:  # 5 articles par source
                    article = {
                        'title': entry.title,
                        'summary': clean_text(getattr(entry, 'summary', '')),
                        'link': entry.link,
                        'source': source_name,
                        'published': getattr(entry, 'published', ''),
                        'image': getattr(entry, 'media_thumbnail', [{}])[0].get('url', '') if hasattr(entry, 'media_thumbnail') else ''
                    }
                    all_articles.append(article)
                    
            except Exception as e:
                logger.error(f"Erreur avec {source_name}: {str(e)}")
                continue
        
        # Trier par source pour un meilleur affichage
        return sorted(all_articles, key=lambda x: x['source'])
        
    except Exception as e:
        logger.error(f"Erreur générale: {str(e)}")
        return []

# ============================================
# ROUTES PRINCIPALES
# ============================================

@app.route('/')
def serve_index():
    """Sert la page d'accueil"""
    return send_from_directory('static', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    """Sert les fichiers statiques"""
    return send_from_directory('static', path)

@app.route('/api/health')
def health_check():
    """Endpoint de santé pour Azure"""
    return jsonify({
        'status': 'healthy',
        'service': 'Voice Assistant API',
        'timestamp': datetime.now().isoformat(),
        'sources_configured': len(NEWS_SOURCES)
    })

@app.route('/api/news')
def get_news():
    """Endpoint pour récupérer les actualités avec filtrage optionnel"""
    try:
        # Récupérer le paramètre topic si présent
        topic = request.args.get('topic', '').lower()
        
        # Utiliser le cache si récent (5 minutes)
        if (news_cache['timestamp'] and 
            (datetime.now() - news_cache['timestamp']).seconds < 300 and 
            news_cache['data']):
            logger.info("Utilisation du cache")
            articles = news_cache['data']
        else:
            # Récupérer les nouvelles actualités
            logger.info("Rafraîchissement des actualités")
            articles = fetch_news()
            # Mettre à jour le cache
            news_cache['data'] = articles
            news_cache['timestamp'] = datetime.now()
        
        # Filtrer par topic si spécifié
        if topic:
            filtered_articles = [
                article for article in articles
                if (topic in article.get('title', '').lower() or 
                    topic in article.get('summary', '').lower() or
                    topic in article.get('source', '').lower())
            ]
            return jsonify(filtered_articles)
        
        return jsonify(articles)
        
    except Exception as e:
        logger.error(f"Erreur API news: {str(e)}")
        return jsonify({'error': 'Erreur serveur'}), 500

@app.route('/api/sources')
def get_sources():
    """Liste les sources disponibles"""
    return jsonify({
        'sources': list(NEWS_SOURCES.keys()),
        'count': len(NEWS_SOURCES)
    })

@app.route('/api/test')
def test_frontend():
    """Endpoint de test pour le frontend"""
    test_data = [
        {
            "title": "🎉 Test Réussi - Frontend Fonctionne !",
            "summary": "Félicitations ! Votre assistant vocal est maintenant opérationnel.",
            "source": "Système",
            "published": datetime.now().isoformat(),
            "link": "#",
            "image": ""
        },
        {
            "title": "🚀 Actualités en Temps Réel", 
            "summary": "Votre application récupère maintenant les dernières actualités depuis plusieurs sources.",
            "source": "Système",
            "published": datetime.now().isoformat(),
            "link": "#",
            "image": ""
        }
    ]
    return jsonify(test_data)

# ============================================
# CONFIGURATION SERVEUR
# ============================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
    logger.info(f"🚀 Démarrage du serveur sur le port {port}")
    app.run(host='0.0.0.0', port=port, debug=debug)