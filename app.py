from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response
import random
import requests
import json
import os
from datetime import datetime, timedelta
from xml.etree import ElementTree

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
CONFIG_PATH = os.path.join(DATA_DIR, 'config.json')
WATCHLIST_FILE = os.path.join(DATA_DIR, 'watchlist.json')

PLEX_PRODUCT = "PlexRouletteApp"
PLEX_CLIENT_IDENTIFIER = "plexroulette-client-001"
PLEX_PLATFORM = "Web"
PLEX_DEVICE_NAME = "PlexRoulette"
PLEX_DEVICE = "PythonApp"
PLEX_VERSION = "1.0"

DEFAULT_SESSION_LIMIT = 20

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'plexroulette-dev-key-change-in-prod')

# Ensure data directory and files exist
os.makedirs(DATA_DIR, exist_ok=True)
if not os.path.exists(CONFIG_PATH):
    with open(CONFIG_PATH, 'w') as f:
        json.dump({}, f)
if not os.path.exists(WATCHLIST_FILE):
    with open(WATCHLIST_FILE, 'w') as f:
        json.dump([], f)

RATING_OPTIONS = [
    'G', 'PG', 'PG-13', 'R', 'NC-17', 'Not Rated', 'Unrated',
    'TV-Y', 'TV-Y7', 'TV-G', 'TV-PG', 'TV-14', 'TV-MA'
]

def load_config():
    if not os.path.exists(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)

def save_config(config):
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=2)

def load_watchlist():
    if not os.path.exists(WATCHLIST_FILE):
        return []
    with open(WATCHLIST_FILE, 'r') as f:
        return json.load(f)

@app.route('/plex_login')
def plex_login():
    headers = {
        'X-Plex-Client-Identifier': PLEX_CLIENT_IDENTIFIER,
        'X-Plex-Product': PLEX_PRODUCT,
        'X-Plex-Version': PLEX_VERSION,
        'X-Plex-Device': PLEX_DEVICE,
        'X-Plex-Platform': PLEX_PLATFORM,
        'X-Plex-Device-Name': PLEX_DEVICE_NAME,
        'Accept': 'application/json'
    }
    try:
        response = requests.post("https://plex.tv/api/v2/pins", headers=headers, timeout=10)
        if response.status_code != 201:
            return "Failed to initiate Plex login", 500
        data = response.json()
    except Exception as e:
        print(f"Plex login error: {e}")
        return "Failed to connect to Plex servers", 500

    session['plex_pin_id'] = data.get("id")
    session['plex_code'] = data.get("code")
    session['plex_expires'] = int(data.get("expires_in", 900))
    return render_template('plex_login.html', code=session['plex_code'], expires_in=session['plex_expires'])

@app.route('/plex_poll')
def plex_poll():
    pin_id = session.get('plex_pin_id')
    if not pin_id:
        return jsonify({'status': 'error', 'message': 'No PIN ID in session'})

    headers = {
        'X-Plex-Client-Identifier': PLEX_CLIENT_IDENTIFIER,
        'X-Plex-Product': PLEX_PRODUCT,
        'X-Plex-Version': PLEX_VERSION,
        'X-Plex-Device': PLEX_DEVICE,
        'X-Plex-Platform': PLEX_PLATFORM,
        'X-Plex-Device-Name': PLEX_DEVICE_NAME,
        'Accept': 'application/json'
    }
    try:
        response = requests.get(f"https://plex.tv/api/v2/pins/{pin_id}", headers=headers, timeout=10)
        data = response.json()
    except Exception as e:
        print(f"Plex poll error: {e}")
        return jsonify({'status': 'error', 'message': 'Failed to connect to Plex'})

    if "errors" in data:
        return jsonify({'status': 'expired'}), 400

    auth_token = data.get("authToken")
    if auth_token:
        session['plex_token'] = auth_token
        config = load_config()
        config['plex_token'] = auth_token

        servers = []
        try:
            server_response = requests.get("https://plex.tv/api/resources?includeHttps=1", headers={
                'X-Plex-Token': auth_token,
                'Accept': 'application/xml'
            }, timeout=10)
            root = ElementTree.fromstring(server_response.text)
            for device in root.findall('Device'):
                name = device.attrib.get('name')
                accessToken = device.attrib.get('accessToken')
                for conn in device.findall('Connection'):
                    if conn.attrib.get('local') == "0" and conn.attrib.get('uri', '').startswith("https://"):
                        servers.append({
                            'name': name,
                            'uri': conn.attrib.get('uri'),
                            'accessToken': accessToken
                        })
                        break
        except Exception as e:
            print(f"Failed to fetch servers: {e}")
        config['plex_servers'] = servers
        if servers:
            config['plex_server_url'] = servers[0]['uri']
            # Fetch libraries from the first server
            try:
                lib_response = requests.get(
                    f"{servers[0]['uri']}/library/sections",
                    headers={'Accept': 'application/json'},
                    params={'X-Plex-Token': servers[0]['accessToken']}
                )
                if lib_response.ok:
                    config['plex_libraries'] = lib_response.json().get('MediaContainer', {}).get('Directory', [])
            except Exception as e:
                print(f"Failed to fetch libraries: {e}")
        save_config(config)
        return jsonify({'status': 'success'})
    return jsonify({'status': 'pending'})

@app.route('/signout')
def signout():
    session.clear()
    config = load_config()
    for key in ['plex_token', 'plex_server_url', 'movies_library', 'tvshows_library', 'plex_servers']:
        config.pop(key, None)
    save_config(config)
    return redirect(url_for('plex_login'))

def get_machine_identifier():
    url = f"{session.get('plex_server_url')}?X-Plex-Token={session.get('plex_token')}"
    try:
        r = requests.get(url)
        r.raise_for_status()
        if 'xml' in r.headers.get('Content-Type', ''):
            root = ElementTree.fromstring(r.text)
            return root.attrib.get('machineIdentifier', 'unknown')
        elif r.headers.get('Content-Type', '').startswith('application/json'):
            return r.json().get('MediaContainer', {}).get('machineIdentifier', 'unknown')
        else:
            print("Unexpected response type in get_machine_identifier():", r.text[:200])
            return 'unknown'
    except Exception as e:
        print(f"Failed to get machine identifier: {e}")
        return 'unknown'

def get_library_key(name):
    if not name:
        return None
    config = load_config()
    libs = config.get('plex_libraries', [])
    return next((lib['key'] for lib in libs if lib['title'] == name), None)

def get_items_from_library(key, unwatched=False):
    if not key:
        return []
    url = f"{session.get('plex_server_url')}/library/sections/{key}/all"
    headers = {'Accept': 'application/json'}
    params = {'X-Plex-Token': session.get('plex_token')}
    if unwatched:
        params['viewCount'] = 0
    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        r.raise_for_status()
        return r.json().get('MediaContainer', {}).get('Metadata', [])
    except Exception as e:
        print(f"Failed to fetch library {key}: {e}")
        return []

def extract_genres(items):
    genres = set()
    for item in items:
        for g in item.get('Genre', []):
            genres.add(g['tag'])
    return sorted(genres)

def build_item_data(item, machine_id):
    rating_key = item.get('ratingKey')
    duration = item.get('duration')
    runtime = int(duration / 60000) if duration else None
    return {
        'title': item.get('title'),
        'year': item.get('year'),
        'summary': item.get('summary', 'No summary available.'),
        'genres': ', '.join([g['tag'] for g in item.get('Genre', [])]) if 'Genre' in item else '',
        'poster': f"{session.get('plex_server_url')}{item.get('thumb')}?X-Plex-Token={session.get('plex_token')}" if item.get('thumb') else '',
        'link': f"{session.get('plex_server_url')}/web/index.html#!/server/{machine_id}/details?key=%2Flibrary%2Fmetadata%2F{rating_key}",
        'rating': item.get('contentRating', 'Unrated'),
        'runtime': str(runtime) if runtime else 'N/A',
        'audience_rating': f"{item.get('audienceRating', 0):.1f}" if item.get('audienceRating') else None,
        'audience_rating_image': item.get('audienceRatingImage')
    }

@app.route('/export_watchlist')
def export_watchlist():
    watchlist = load_watchlist()
    export_format = request.args.get('format', 'json')
    if export_format == 'csv':
        headers = ['title', 'year', 'summary', 'genres', 'poster', 'link', 'rating', 'runtime', 'audience_rating']
        output = [headers] + [[item.get(h, '') for h in headers] for item in watchlist]
        lines = []
        for row in output:
            cells = ['"{}"'.format(str(cell).replace('"', '""')) for cell in row]
            lines.append(','.join(cells))
        csv_text = '\n'.join(lines)
        return Response(csv_text, mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=watchlist.csv'})
    return Response(json.dumps(watchlist, indent=2), mimetype='application/json', headers={'Content-Disposition': 'attachment; filename=watchlist.json'})

@app.route('/', methods=['GET', 'POST'])
def index():
    config = load_config()

    if not session.get('plex_token') and config.get('plex_token'):
        session['plex_token'] = config['plex_token']
    if not session.get('plex_server_url') and config.get('plex_server_url'):
        session['plex_server_url'] = config['plex_server_url']

    if 'theme' not in session:
        session['theme'] = config.get('default_theme', 'dark')
    if 'enable_history' not in config:
        config['enable_history'] = True

    if not session.get("plex_token") or not session.get("plex_server_url"):
        return redirect(url_for('plex_login'))

    if not config.get("movies_library") and not config.get("tvshows_library"):
        return redirect(url_for('settings'))

    movie_key = get_library_key(config.get("movies_library"))
    show_key = get_library_key(config.get("tvshows_library"))
    machine_id = get_machine_identifier()
    items = []

    if movie_key:
        items += get_items_from_library(movie_key)
    if show_key:
        items += get_items_from_library(show_key)

    genres = extract_genres(items)
    form = request.form
    results = []

    if request.method == 'POST':
        if 'toggle_history' in form:
            session['show_history'] = not session.get('show_history', False)
        elif 'clear_history' in form:
            session['pick_history'] = []
        elif 'add_to_watchlist' in form:
            item = {
                'title': form.get('saved_title'),
                'year': form.get('saved_year'),
                'summary': form.get('saved_summary'),
                'genres': form.get('saved_genres'),
                'poster': form.get('saved_poster'),
                'link': form.get('saved_link'),
                'rating': form.get('saved_rating'),
                'runtime': form.get('saved_runtime'),
                'audience_rating': form.get('saved_audience_rating')
            }
            if item['title'] and item['year']:
                watchlist = load_watchlist()
                if not any(w['title'] == item['title'] and str(w['year']) == str(item['year']) for w in watchlist):
                    watchlist.append(item)
                    with open(WATCHLIST_FILE, 'w') as f:
                        json.dump(watchlist, f, indent=2)
        else:
            media_type = form.get('media_type', 'both')
            unwatched = 'unwatched' in form
            filtered = []

            if media_type == 'movie' and movie_key:
                filtered += get_items_from_library(movie_key, unwatched=unwatched)
            elif media_type == 'show' and show_key:
                filtered += get_items_from_library(show_key, unwatched=unwatched)
            else:
                if movie_key:
                    filtered += get_items_from_library(movie_key, unwatched=unwatched)
                if show_key:
                    filtered += get_items_from_library(show_key, unwatched=unwatched)

            if form.get('genre'):
                filtered = [i for i in filtered if any(g['tag'] == form.get('genre') for g in i.get('Genre', []))]
            if form.get('rating'):
                filtered = [i for i in filtered if i.get('contentRating') == form.get('rating')]
            if form.get('keyword'):
                filtered = [i for i in filtered if form.get('keyword').lower() in i.get('summary', '').lower()]
            if form.get('recent_releases'):
                cutoff = datetime.now() - timedelta(days=5 * 365)
                filtered = [i for i in filtered if i.get('originallyAvailableAt') and datetime.strptime(i.get('originallyAvailableAt'), "%Y-%m-%d") > cutoff]

            picks = 3 if 'show_three' in form else 1
            results = [build_item_data(i, machine_id) for i in random.sample(filtered, min(picks, len(filtered)))]

            session['current_results'] = results
            if config.get('enable_history', True):
                history = session.setdefault('pick_history', [])
                history.extend(results)
                session['pick_history'] = history[-DEFAULT_SESSION_LIMIT:]

    return render_template('index.html',
                           results=session.get('current_results', []),
                           genres=genres,
                           rating_options=RATING_OPTIONS,
                           pick_history=session.get('pick_history', []),
                           show_history=session.get('show_history', False),
                           default_theme=config.get("default_theme", "dark"),
                           config=config)

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    config = load_config()
    if request.method == 'POST':
        server_uri = request.form.get('plex_server_url')
        selected_server = next((s for s in config.get('plex_servers', []) if s['uri'] == server_uri), None)
        config['plex_server_url'] = selected_server['uri'] if selected_server else server_uri
        config['movies_library'] = request.form.get('movies_library') or None
        config['tvshows_library'] = request.form.get('tvshows_library') or None
        config['default_theme'] = request.form.get('default_theme', 'dark')
        config['enable_history'] = 'enable_history' in request.form
        save_config(config)

        session['plex_token'] = config.get('plex_token')
        session['plex_server_url'] = config.get('plex_server_url')
        session['theme'] = config.get('default_theme', 'dark')

        return redirect(url_for('index'))

    return render_template('settings.html',
                           config=config,
                           libraries=config.get('plex_libraries', []),
                           servers=config.get('plex_servers', []),
                           default_theme=config.get("default_theme", "dark"))

@app.route('/watchlist', methods=['GET', 'POST'])
def watchlist():
    if request.method == 'POST':
        title = request.form.get('title')
        year = request.form.get('year')
        if title and year:
            watchlist = load_watchlist()
            updated = [item for item in watchlist if not (item['title'] == title and str(item['year']) == str(year))]
            with open(WATCHLIST_FILE, 'w') as f:
                json.dump(updated, f, indent=2)
        return redirect(url_for('watchlist'))

    return render_template('watchlist.html',
                           watchlist=load_watchlist(),
                           default_theme=load_config().get("default_theme", "dark"))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(debug=debug, host='0.0.0.0', port=port)
