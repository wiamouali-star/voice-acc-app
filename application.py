# ============================================
# ASSISTANT VOCAL INTELLIGENT - Backend Flask
# Version optimisée et corrigée pour Azure App Service
# ============================================

from flask import Flask, send_from_directory, request, jsonify
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from datetime import datetime, timedelta
import os
import re
import feedparser
import logging
from dotenv import load_dotenv
import json
import unicodedata
import csv
import threading
import requests


# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='static', static_url_path='')

# Configuration CORS
CORS(app)

load_dotenv()
DIRECT_LINE_SECRET = os.environ["DIRECT_LINE_SECRET"]

# Configuration Flask-Limiter avec stockage mémoire (OK pour développement)
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# ============================================
# CONFIGURATION DES SOURCES RSS
# ============================================
NEWS_SOURCES = {
    "Le Monde": "https://www.lemonde.fr/rss/une.xml",
    "France 24": "https://www.france24.com/fr/rss", 
    "BBC News": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "20 Minutes": "https://www.20minutes.fr/feeds/rss-une.xml"
}

# Cache simple
news_cache = {
    'data': None,
    'timestamp': None,
    'duration': timedelta(minutes=5)
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

def _normalize_text(s: str) -> str:
    """Normalise le texte pour les comparaisons (enlève accents)"""
    if not s:
        return ""
    s = s.lower().strip()
    # Supprimer accents pour correspondances plus permissives
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return s

def fetch_news():
    """Fetch news from all configured sources with better error handling"""
    try:
        all_articles = []
        logger.info("Starting news fetch from sources")
        
        for source_name, source_url in NEWS_SOURCES.items():
            try:
                logger.info(f"Fetching from {source_name}: {source_url}")
                feed = feedparser.parse(source_url)
                
                # Vérification améliorée du flux
                if feed.bozo:
                    logger.warning(f"Feed error for {source_name}: {feed.bozo_exception}")
                    # Ajouter un article d'erreur pour informer l'utilisateur
                    all_articles.append({
                        'title': f"[Problème] {source_name} - Flux temporairement indisponible",
                        'summary': f"Impossible de récupérer les actualités de {source_name}",
                        'link': '',
                        'published': datetime.now().isoformat(),
                        'source': source_name,
                        'tags': ['erreur']
                    })
                    continue
                
                if not feed.entries:
                    logger.warning(f"No entries found for {source_name}")
                    continue
                
                for entry in feed.entries[:5]:  # Limite à 5 articles par source
                    try:
                        # Nettoyage des données
                        title = entry.get('title', 'Sans titre')
                        summary = clean_text(entry.get('summary', entry.get('description', '')))
                        link = entry.get('link', '')
                        
                        # Gestion de la date
                        published = entry.get('published', '')
                        if not published and hasattr(entry, 'updated'):
                            published = entry.updated
                        
                        article = {
                            'title': title,
                            'summary': summary,
                            'link': link,
                            'published': published,
                            'source': source_name,
                            'tags': [tag.term for tag in entry.get('tags', [])] if hasattr(entry, 'tags') else []
                        }
                        all_articles.append(article)
                        
                    except Exception as e:
                        logger.error(f"Error processing article from {source_name}: {e}")
                        continue
                
                logger.info(f"Successfully processed {len(feed.entries[:5])} articles from {source_name}")
                
            except Exception as e:
                logger.error(f"Error fetching from {source_name}: {str(e)}")
                continue
                
        logger.info(f"Total articles processed: {len(all_articles)}")
        return all_articles
        
    except Exception as e:
        logger.error(f"Critical error in fetch_news: {str(e)}")
        # Retourner des données de fallback
        return [{
            'title': 'Actualités temporairement indisponibles',
            'summary': 'Nous rencontrons des difficultés techniques. Veuillez réessayer dans quelques instants.',
            'source': 'Système',
            'published': datetime.now().isoformat(),
            'link': '',
            'tags': ['erreur']
        }]

def get_cached_news():
    """Récupère les actualités du cache si valides"""
    now = datetime.now()
    if (news_cache['data'] is not None and 
        news_cache['timestamp'] is not None and
        now - news_cache['timestamp'] < news_cache['duration']):
        return news_cache['data']
    return None

# ============================================
# CONFIGURATION MISTRAL AI
# ============================================

# Charger variables d'environnement
load_dotenv()

# Configuration Mistral - Gestion sécurisée
try:
    from mistralai.client import MistralClient
    mistral_api_key = os.getenv("MISTRAL_API_KEY")
    if mistral_api_key:
        mistral = MistralClient(api_key=mistral_api_key)
        logger.info("Mistral client initialized successfully")
    else:
        mistral = None
        logger.warning("MISTRAL_API_KEY not found, Mistral features disabled")
except ImportError:
    logger.warning("MistralAI package not installed, Mistral features disabled")
    mistral = None
except Exception as e:
    logger.error(f"Failed to initialize Mistral client: {e}")
    mistral = None

# Liste des catégories autorisées
CLASSIFIER_CATEGORIES = [
    "politique", "économie", "sport", "culture",
    "santé", "technologie", "environnement", "international",
    "science", "éducation", "voyages", "loisirs",
    "business", "justice", "sécurité", "météo",
    "divertissement", "startup", "immobilier", "automobile",
    "alimentaire", "mode", "santé-mentale", "énergie",
    "autre"
]

# Map de termes associés pour recherche élargie
CATEGORY_TERMS = {
    "sport": ["football", "tennis", "rugby", "olympique", "coupe", "championnat", "sportif", "sports"],
    "politique": ["gouvernement", "assemblée", "président", "ministre", "élection", "parlement", "politique"],
    "économie": ["finance", "bourse", "entreprise", "marché", "budget", "inflation", "économique", "économie"],
    "culture": ["culture", "art", "cinéma", "musique", "exposition", "théâtre", "livre"],
    "santé": ["santé", "médecine", "hôpital", "vaccin", "épidémie", "bien-être"],
    "technologie": ["technologie", "tech", "ia", "intelligence artificielle", "numérique", "startup"],
    "environnement": ["climat", "écologie", "pollution", "biodiversité", "recyclage", "environnement"],
    "international": ["international", "étranger", "diplomatie", "monde", "relations internationales"],
    "science": ["science", "recherche", "découverte", "physique", "biologie"],
    "éducation": ["éducation", "école", "université", "enseignement", "formation"],
    "voyages": ["voyage", "tourisme", "vol", "destination", "hôtel"],
    "loisirs": ["loisir", "hobby", "jeux", "événement", "festival"],
    "business": ["business", "entrepreneuriat", "startup", "investissement"],
    "justice": ["justice", "tribunal", "procès", "juridique"],
    "sécurité": ["sécurité", "police", "terrorisme", "sécurité nationale"],
    "météo": ["météo", "tempête", "climat", "alerte"],
    "divertissement": ["divertissement", "people", "télévision", "cinéma", "série"],
    "startup": ["startup", "levée de fonds", "incubateur"],
    "immobilier": ["immobilier", "logement", "prix immobilier"],
    "automobile": ["automobile", "voiture", "autonomie", "véhicule"],
    "alimentaire": ["alimentaire", "restauration", "nutrition", "aliment"],
    "mode": ["mode", "fashion", "défilé", "créateur"],
    "santé-mentale": ["dépression", "bien-être mental", "psychologie"],
    "énergie": ["énergie", "pétrole", "gazière", "renouvelable"],
    "autre": []
}

classification_cache = {}

def classify_query_with_mistral(query):
    """Classifie la requête utilisateur - Version CORRIGÉE"""
    if not query:
        return "autre", "no_query"
    
    logger.info(f"Classifying query: {query!r}")
    
    # Si Mistral n'est pas disponible, utiliser le fallback immédiatement
    if mistral is None:
        logger.info("Mistral not available, using keyword fallback")
        return classify_with_keywords(query), "mistral_unavailable"
    
    try:
        # Version CORRIGÉE de l'appel Mistral
        chat_response = mistral.chat(
            model="mistral-tiny",
            messages=[
                {
                    "role": "system", 
                    "content": "Tu es un classificateur de requêtes. Réponds UNIQUEMENT par un de ces mots: politique, économie, sport, culture, santé, technologie, environnement, international, science, éducation, voyages, loisirs, business, justice, sécurité, météo, divertissement, startup, immobilier, automobile, alimentaire, mode, santé-mentale, énergie, autre."
                },
                {
                    "role": "user", 
                    "content": f"Dans quelle catégorie classer cette recherche d'actualités: \"{query}\""
                }
            ],
            temperature=0.1,
            max_tokens=10
        )
        
        # Extraction CORRIGÉE de la réponse
        if hasattr(chat_response, 'choices') and chat_response.choices:
            raw_text = chat_response.choices[0].message.content
        else:
            # Gestion alternative
            raw_text = str(getattr(chat_response, 'content', ''))
        
        raw_text = raw_text.strip().lower()
        logger.info(f"Mistral raw response: {raw_text!r}")
        
        # Recherche de catégorie dans la réponse
        for category in CLASSIFIER_CATEGORIES:
            if category in raw_text:
                logger.info(f"Mistral classified as: {category}")
                return category, raw_text
                
        # Si aucune catégorie trouvée
        return classify_with_keywords(query), f"no_category_found:{raw_text}"
        
    except Exception as e:
        logger.warning(f"Mistral call failed: {e}")
        return classify_with_keywords(query), f"mistral_error:{str(e)}"
    


def classify_with_keywords(query):
    """Classification par mots-clés (fallback)"""
    qlow = _normalize_text(query)
    for valid in CLASSIFIER_CATEGORIES:
        vnorm = _normalize_text(valid)
        if re.search(rf'\b{re.escape(vnorm)}s?\b', qlow):
            logger.info(f"Keyword fallback matched '{valid}' for query {query!r}")
            return valid
    return "autre"

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
    mistral_status = "enabled" if mistral else "disabled"
    return jsonify({
        'status': 'healthy',
        'service': 'Voice Assistant API',
        'timestamp': datetime.now().isoformat(),
        'sources_configured': len(NEWS_SOURCES),
        'mistral_ai': mistral_status,
        'version': '2.0.0'
    })

@app.route('/api/news')
@limiter.limit("30 per minute")
def get_news():
    """Endpoint principal pour les actualités avec gestion d'erreurs"""
    try:
        topic = request.args.get('topic', '').lower().strip()
        source_filter = request.args.get('source', '').lower()
        limit = int(request.args.get('limit', 20))
        
        # Journalisation uniquement pour les recherches significatives
        if topic and len(topic) > 2 and request.args.get('logged') != '1':
            try:
                log_search(topic, topic, method="direct")
            except Exception as e:
                logger.warning(f"Failed to log search: {e}")

        # Récupération des articles
        articles = fetch_news()
        logger.info(f"Total articles fetched before filtering: {len(articles)}")
        
        # Filtrage par topic AMÉLIORÉ
        if topic:
            articles = filter_articles_by_topic(articles, topic)
            logger.info(f"Articles after topic filtering '{topic}': {len(articles)}")
        
        # Filtrage par source
        if source_filter:
            articles = [a for a in articles if source_filter in a.get('source', '').lower()]
        
        # Limitation
        articles = articles[:limit]
        
        logger.info(f"Final articles to return: {len(articles)}")
        return jsonify(articles)
        
    except ValueError as e:
        logger.error(f"Invalid parameter: {e}")
        return jsonify({'error': 'Paramètre invalide'}), 400
    except Exception as e:
        logger.error(f"Error in /api/news: {str(e)}")
        return jsonify({'error': 'Erreur interne du serveur'}), 500


@app.route('/api/sources')
def get_sources():
    """Liste les sources disponibles"""
    return jsonify({
        'sources': list(NEWS_SOURCES.keys()),
        'count': len(NEWS_SOURCES),
        'last_updated': datetime.now().isoformat()
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
            "image": "",
            "tags": ["test", "succès"]
        },
        {
            "title": "🚀 Actualités en Temps Réel", 
            "summary": "Votre application récupère maintenant les dernières actualités depuis plusieurs sources.",
            "source": "Système",
            "published": datetime.now().isoformat(),
            "link": "#", 
            "image": "",
            "tags": ["test", "fonctionnalité"]
        }
    ]
    return jsonify(test_data)


@app.route("/api/bot-token", methods=['GET'])
def get_bot_token():
    """Retourne le token Direct Line - SOLUTION FONCTIONNELLE"""
    try:
        direct_line_secret = os.getenv('DIRECT_LINE_SECRET')
        
        if not direct_line_secret:
            logger.error("DIRECT_LINE_SECRET non configurée")
            return jsonify({"error": "Configuration bot manquante"}), 500
        
        logger.info("✅ Utilisation du secret Direct Line comme token")
        
        # Dans certains cas, le secret peut être utilisé directement comme token
        return jsonify({
            'token': direct_line_secret,
            'conversationId': f'conv_{datetime.now().strftime("%Y%m%d%H%M%S")}_{os.urandom(4).hex()}',
            'expires_in': 3600
        })
            
    except Exception as e:
        logger.error(f"❌ Erreur: {str(e)}")
        return jsonify({"error": f"Erreur: {str(e)}"}), 500

@app.route('/api/debug-bot')
def debug_bot_config():
    """Route de débogage pour la configuration bot"""
    direct_line_secret = os.getenv('DIRECT_LINE_SECRET')
    
    debug_info = {
        'direct_line_secret_configured': bool(direct_line_secret),
        'direct_line_secret_length': len(direct_line_secret) if direct_line_secret else 0,
        'direct_line_secret_prefix': direct_line_secret[:10] + '...' if direct_line_secret else None,
        'timestamp': datetime.now().isoformat()
    }
    
    logger.info(f"🔍 Debug bot config: {debug_info}")
    return jsonify(debug_info)


# ============================================
# ROUTES BOT INTÉGRÉES DANS FLASK
# ============================================

from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings
from botbuilder.schema import Activity
import asyncio

# Configuration du bot
bot_settings = BotFrameworkAdapterSettings("", "")  # Sans auth pour le moment
bot_adapter = BotFrameworkAdapter(bot_settings)

@app.route("/api/messages", methods=["POST", "OPTIONS"])
def messages():
    """Version ultra-simplifiée pour tester"""
    try:
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200
            
        body = request.get_json()
        logger.info(f"Message reçu: {body}")
        
        # Réponse simple immédiate
        response = {
            "type": "message",
            "text": "✅ Bonjour ! Je suis votre bot Flask qui fonctionne !",
            "from": {"id": "bot", "name": "Flask Bot"},
            "recipient": {"id": "user"}
        }
        
        return jsonify(response), 200
        
    except Exception as e:
        logger.error(f"Erreur: {e}")
        return jsonify({"error": str(e)}), 500

async def bot_logic(context):
    """Logique de votre bot"""
    if context.activity.type == "message":
        await context.send_activity(f"Bot dit: Vous avez dit '{context.activity.text}'")
    elif context.activity.type == "event" and context.activity.name == "newsSelected":
        news = context.activity.value
        await context.send_activity(f"📰 Article sélectionné: {news['title']}")

# ============================================
# CLASSIFICATION AVEC VALIDATION
# ============================================

try:
    from marshmallow import Schema, fields, validate, ValidationError
    
    class QuerySchema(Schema):
        query = fields.Str(required=True, validate=validate.Length(min=1, max=500))

except ImportError:
    logger.warning("Marshmallow not installed, using basic validation")
    # Fallback basique si marshmallow n'est pas installé
    class QuerySchema:
        @staticmethod
        def load(data):
            query = data.get('query', '').strip()
            if not query or len(query) > 500:
                raise ValueError("Query must be between 1 and 500 characters")
            return {'query': query}

@app.route('/api/classify', methods=['POST'])
@limiter.limit("10 per minute")
def classify_endpoint():
    """Endpoint pour classifier une requête"""
    try:
        req_json = request.get_json(silent=True)
        
        # Si silent a renvoyé None, tenter d'extraire le corps brut et parser
        if req_json is None:
            raw_text = request.get_data(as_text=True) or ""
            if not raw_text:
                logger.warning("Classification request missing body or invalid JSON")
                return jsonify({"error": "missing_json", "message": "Le corps JSON est manquant."}), 400
            try:
                req_json = json.loads(raw_text)
            except Exception as e:
                logger.warning(f"Invalid JSON received: {raw_text!r}")
                return jsonify({"error": "invalid_json", "message": "JSON invalide reçu.", "received": raw_text}), 400

        # Valider le schéma
        try:
            schema = QuerySchema()
            data = schema.load(req_json)
        except ValidationError as err:
            return jsonify({"error": "validation_error", "message": str(err)}), 400
        except ValueError as err:
            return jsonify({"error": "validation_error", "message": str(err)}), 400

        query = data.get('query', '')
        category, raw = classify_query_with_mistral(query)
        
        # Journalisation
        try:
            log_search(query, category, method="classify")
        except Exception as e:
            logger.warning(f"Failed to log search: {e}")
            
        logger.info(f"Classification result for {query!r}: {category} (raw={raw!r})")
        return jsonify({
            "category": category, 
            "raw": raw,
            "query": query,
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.exception("Classification endpoint error")
        return jsonify({"error": "internal_error", "message": str(e)}), 500

# ============================================
# JOURNALISATION DES RECHERCHES dans azure blob
# ============================================

from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import AzureError
import io

# Configuration Azure Blob Storage
AZURE_STORAGE_CONNECTION_STRING = os.getenv('AZURE_STORAGE_CONNECTION_STRING')
AZURE_CONTAINER_NAME = os.getenv('AZURE_CONTAINER_NAME', 'search-logs')
AZURE_BLOB_NAME = 'search_log.csv'

# Cache du client Blob pour réutilisation
_blob_client = None


_csv_lock = threading.Lock()

def _get_blob_client():
    """Obtient ou crée un client Blob Storage."""
    global _blob_client
    
    if _blob_client is None and AZURE_STORAGE_CONNECTION_STRING:
        try:
            # Créer le client de service Blob
            blob_service = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
            
            # Créer le conteneur s'il n'existe pas
            try:
                container_client = blob_service.create_container(AZURE_CONTAINER_NAME)
            except Exception:
                container_client = blob_service.get_container_client(AZURE_CONTAINER_NAME)
            
            # Obtenir le client pour notre blob
            _blob_client = container_client.get_blob_client(AZURE_BLOB_NAME)
            
            # Créer le fichier avec l'en-tête s'il n'existe pas
            try:
                _blob_client.get_blob_properties()
            except Exception:
                header = "timestamp_utc,query,category,method\n"
                _blob_client.upload_blob(header, blob_type="AppendBlob", overwrite=True)
                
            logger.info("Azure Blob Storage client initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Azure Blob Storage: {e}")
            _blob_client = None
    
    return _blob_client

def log_search(query, category, method="unknown"):
    """Enregistre une recherche dans Azure Blob Storage."""
    try:
        blob_client = _get_blob_client()
        if not blob_client:
            logger.warning("Azure Blob Storage not configured, logging disabled")
            return
            
        ts = datetime.utcnow().isoformat() + "Z"
        
        # Créer la ligne CSV
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([ts, query, category, method])
        log_line = output.getvalue()
        
        # Ajouter au blob de manière thread-safe
        with _csv_lock:
            try:
                blob_client.append_block(log_line)
                logger.info(f"Logged search to Azure: {ts} | {query!r} -> {category!r} ({method})")
            except Exception as e:
                if "BlobNotFound" in str(e):
                    # Le blob n'existe pas, on le crée
                    header = "timestamp_utc,query,category,method\n"
                    blob_client.upload_blob(header + log_line, blob_type="AppendBlob", overwrite=True)
                else:
                    raise
                    
    except Exception as e:
        logger.warning(f"Failed to log search to Azure: {e}")
        # En cas d'erreur, on continue l'exécution normale de l'application


def filter_articles_by_topic(articles, topic):
    """Filtre les articles par topic avec recherche élargie et correspondances partielles"""
    if not topic:
        return articles
    
    filtered_articles = []
    topic_lower = topic.lower().strip()
    
    # Map des synonymes et termes associés
    topic_synonyms = {
        'sport': ['sport', 'football', 'tennis', 'rugby', 'basket', 'athlétisme', 'championnat', 'match', 'joueur', 'équipe', 'coupe', 'olympique'],
        'politique': ['politique', 'gouvernement', 'président', 'ministre', 'élection', 'parlement', 'assemblée', 'parti', 'vote', 'député'],
        'économie': ['économie', 'économique', 'finance', 'bourse', 'entreprise', 'marché', 'budget', 'inflation', 'euro', 'dollar'],
        'technologie': ['technologie', 'tech', 'numérique', 'internet', 'smartphone', 'ordinateur', 'ia', 'intelligence artificielle', 'innovation'],
        'santé': ['santé', 'médecin', 'hôpital', 'maladie', 'vaccin', 'médical', 'patient', 'traitement'],
        'culture': ['culture', 'culturel', 'art', 'musée', 'exposition', 'livre', 'film', 'cinéma', 'musique', 'théâtre'],
        'environnement': ['environnement', 'écologie', 'climat', 'réchauffement', 'pollution', 'vert', 'durable'],
        'international': ['international', 'monde', 'étranger', 'diplomatie', 'onu', 'conflit', 'paix']
    }
    
    # Obtenir tous les termes de recherche pour ce topic
    search_terms = topic_synonyms.get(topic_lower, [topic_lower])
    
    for article in articles:
        try:
            # Préparer le texte de recherche
            title = article.get('title', '').lower()
            summary = article.get('summary', '').lower()
            source = article.get('source', '').lower()
            tags = [tag.lower() for tag in article.get('tags', [])]
            
            # Texte combiné pour la recherche
            search_text = f"{title} {summary} {source} {' '.join(tags)}"
            
            # Rechercher n'importe lequel des termes associés
            found = any(term in search_text for term in search_terms)
            
            if found:
                filtered_articles.append(article)
                logger.info(f"✅ Article match: '{title}' with terms {search_terms}")
                
        except Exception as e:
            logger.error(f"Error filtering article: {e}")
            continue
    
    logger.info(f"🔍 Filtered {len(filtered_articles)} articles for topic '{topic}' with terms {search_terms}")
    return filtered_articles


@app.route('/app.js')
def serve_js():
    return send_from_directory('static', 'app.js')

@app.route('/style.css')
def serve_css():
    return send_from_directory('static', 'style.css')



@app.route('/api/test-filter')
def test_filter():
    """Route de test pour le filtrage"""
    test_articles = [
        {
            "title": "Test Sport - Match de football",
            "summary": "Un grand match de sport a eu lieu ce weekend",
            "source": "Test Source",
            "published": datetime.now().isoformat(),
            "link": "#",
            "tags": ["sport", "football"]
        },
        {
            "title": "Test Politique - Élections",
            "summary": "Les élections politiques approchent",
            "source": "Test Source", 
            "published": datetime.now().isoformat(),
            "link": "#",
            "tags": ["politique"]
        },
        {
            "title": "Test Technologie - Nouveau smartphone",
            "summary": "Un nouveau smartphone révolutionnaire",
            "source": "Test Source",
            "published": datetime.now().isoformat(), 
            "link": "#",
            "tags": ["technologie"]
        }
    ]
    
    topic = request.args.get('topic', '')
    if topic:
        filtered = filter_articles_by_topic(test_articles, topic)
        return jsonify({
            "topic": topic,
            "total": len(test_articles),
            "filtered": len(filtered),
            "articles": filtered
        })
    
    return jsonify(test_articles)

# ============================================
# CONFIGURATION SERVEUR
# ============================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
    logger.info(f"🚀 Démarrage du serveur sur le port {port}")
    logger.info(f"📰 Sources configurées: {len(NEWS_SOURCES)}")
    logger.info(f"🤖 Mistral AI: {'Activé' if mistral else 'Désactivé'}")
    
    app.run(host='0.0.0.0', port=port, debug=debug)
