"""
elogicode.ro - Instrument Actualizare Prețuri Shopify
Flask backend cu OAuth 2.0 pentru Shopify Dev Dashboard apps
"""

from flask import Flask, render_template, request, jsonify, redirect
import requests
import json
import os
import re
import hmac
import hashlib
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

app = Flask(__name__)

CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'config.json')
API_VERSION = '2024-07'
REDIRECT_URI = 'http://127.0.0.1:5000/oauth/callback'
SCOPES = 'read_products,write_products,read_inventory'


# ─── Config helpers ──────────────────────────────────────────────────────────

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_config_to_file(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


# ─── Shopify API helpers ──────────────────────────────────────────────────────

def shopify_get(endpoint, config, params=None):
    store_url = config.get('store_url', '').rstrip('/')
    token = config.get('access_token', '')
    url = f"{store_url}/admin/api/{API_VERSION}/{endpoint}"
    headers = {'X-Shopify-Access-Token': token, 'Content-Type': 'application/json'}
    return requests.get(url, headers=headers, params=params, timeout=30)


def shopify_put(endpoint, config, data):
    store_url = config.get('store_url', '').rstrip('/')
    token = config.get('access_token', '')
    url = f"{store_url}/admin/api/{API_VERSION}/{endpoint}"
    headers = {'X-Shopify-Access-Token': token, 'Content-Type': 'application/json'}
    return requests.put(url, headers=headers, json=data, timeout=30)


def fetch_all_products(config):
    all_products = []
    params = {'limit': 250, 'fields': 'id,title,product_type,handle,tags,variants'}
    while True:
        resp = shopify_get('products.json', config, params=params)
        if resp.status_code != 200:
            return None, f"Eroare Shopify {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        products = data.get('products', [])
        all_products.extend(products)
        link = resp.headers.get('Link', '')
        if 'rel="next"' not in link:
            break
        match = re.search(r'<[^>]*[?&]page_info=([^&>]+)[^>]*>;\s*rel="next"', link)
        if not match:
            break
        params = {'limit': 250, 'page_info': match.group(1)}
    return all_products, None


def fetch_all_collections(config):
    collections = []
    for ctype in ('custom_collections', 'smart_collections'):
        resp = shopify_get(f'{ctype}.json', config, params={'limit': 250})
        if resp.status_code == 200:
            collections.extend(resp.json().get(ctype, []))
    return collections


def fetch_collects(config):
    product_to_collections = {}
    params = {'limit': 250}
    while True:
        resp = shopify_get('collects.json', config, params=params)
        if resp.status_code != 200:
            break
        data = resp.json()
        collects = data.get('collects', [])
        if not collects:
            break
        for c in collects:
            product_to_collections.setdefault(c['product_id'], []).append(c['collection_id'])
        link = resp.headers.get('Link', '')
        if 'rel="next"' not in link:
            break
        match = re.search(r'<[^>]*[?&]page_info=([^&>]+)[^>]*>;\s*rel="next"', link)
        if not match:
            break
        params = {'limit': 250, 'page_info': match.group(1)}
    return product_to_collections


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


# ── OAuth Flow ────────────────────────────────────────────────────────────────

@app.route('/install')
def install():
    """Pasul 1: Redirecționează spre Shopify pentru autorizare."""
    cfg = load_config()
    client_id = cfg.get('client_id', '')
    store_url = cfg.get('store_url', '').rstrip('/')

    if not client_id or not store_url:
        return "<h3>Eroare: Client ID și Store URL lipsă. Configurează mai întâi în aplicație.</h3>", 400

    shop = store_url.replace('https://', '').replace('http://', '')
    auth_url = (
        f"https://{shop}/admin/oauth/authorize"
        f"?client_id={client_id}"
        f"&scope={SCOPES}"
        f"&redirect_uri={REDIRECT_URI}"
    )
    return redirect(auth_url)


@app.route('/oauth/callback')
def oauth_callback():
    """Pasul 2: Shopify redirecționează aici cu codul de autorizare."""
    code = request.args.get('code')
    shop = request.args.get('shop')

    if not code or not shop:
        return "<h3>Eroare OAuth: parametri lipsă (code/shop)</h3>", 400

    cfg = load_config()
    client_id = cfg.get('client_id', '')
    client_secret = cfg.get('client_secret', '')

    if not client_id or not client_secret:
        return "<h3>Eroare: Client ID sau Secret lipsă în configurație.</h3>", 400

    # Schimbă codul pe access token
    r = requests.post(
        f"https://{shop}/admin/oauth/access_token",
        json={'client_id': client_id, 'client_secret': client_secret, 'code': code},
        timeout=15
    )

    if r.status_code == 200:
        token = r.json().get('access_token', '')
        cfg['access_token'] = token
        cfg['store_url'] = f'https://{shop}'
        save_config_to_file(cfg)
        return redirect('/?connected=1')
    else:
        return f"<h3>Eroare la obținerea tokenului: {r.status_code} – {r.text}</h3>", 400


# ── Config API ────────────────────────────────────────────────────────────────

@app.route('/api/config', methods=['GET'])
def get_config():
    cfg = load_config()
    return jsonify({
        'store_url': cfg.get('store_url', ''),
        'client_id': cfg.get('client_id', ''),
        'has_secret': bool(cfg.get('client_secret', '')),
        'has_token': bool(cfg.get('access_token', ''))
    })


@app.route('/api/config', methods=['POST'])
def save_config():
    data = request.json or {}
    cfg = load_config()
    if 'store_url' in data:
        cfg['store_url'] = data['store_url'].rstrip('/')
    if 'client_id' in data and data['client_id']:
        cfg['client_id'] = data['client_id']
    if 'client_secret' in data and data['client_secret']:
        cfg['client_secret'] = data['client_secret']
    save_config_to_file(cfg)
    return jsonify({'status': 'ok'})


@app.route('/api/disconnect', methods=['POST'])
def disconnect():
    cfg = load_config()
    cfg.pop('access_token', None)
    save_config_to_file(cfg)
    return jsonify({'status': 'ok'})


# ── Test ──────────────────────────────────────────────────────────────────────

@app.route('/api/test')
def test_connection():
    cfg = load_config()
    store_url = cfg.get('store_url', '').rstrip('/')
    token = cfg.get('access_token', '')
    if not store_url or not token:
        return jsonify({'error': 'Configurație lipsă'}), 400
    url = f"{store_url}/admin/api/{API_VERSION}/shop.json"
    try:
        r = requests.get(url, headers={'X-Shopify-Access-Token': token}, timeout=10)
        return jsonify({'url_called': url, 'status_code': r.status_code,
                        'response': r.json() if 'json' in r.headers.get('content-type','') else r.text[:300]})
    except Exception as e:
        return jsonify({'url_called': url, 'error': str(e)})


# ── Products & Prices ─────────────────────────────────────────────────────────

@app.route('/api/products')
def get_products():
    cfg = load_config()
    if not cfg.get('store_url') or not cfg.get('access_token'):
        return jsonify({'error': 'Neconectat. Apasă "Conectează cu Shopify" mai întâi.'}), 400

    products, err = fetch_all_products(cfg)
    if err:
        return jsonify({'error': err}), 400

    collections = fetch_all_collections(cfg)
    col_id_to_title = {c['id']: c['title'] for c in collections}
    product_to_cols = fetch_collects(cfg)

    result = []
    for p in products:
        col_ids = product_to_cols.get(p['id'], [])
        category = col_id_to_title.get(col_ids[0], p.get('product_type') or 'Fără categorie') if col_ids else (p.get('product_type') or 'Fără categorie')

        for v in p.get('variants', []):
            variant_title = v.get('title', '')
            if variant_title == 'Default Title':
                variant_title = ''
            result.append({
                'product_id': p['id'],
                'product_title': p['title'],
                'variant_id': v['id'],
                'variant_title': variant_title,
                'sku': v.get('sku') or '',
                'price': v.get('price', '0.00'),
                'compare_at_price': v.get('compare_at_price') or '',
                'category': category,
            })

    result.sort(key=lambda x: (x['category'].lower(), x['product_title'].lower(), x['variant_title']))
    return jsonify({'products': result, 'total': len(result)})


@app.route('/api/update-price', methods=['POST'])
def update_price():
    cfg = load_config()
    if not cfg.get('access_token'):
        return jsonify({'error': 'Neconectat'}), 400
    data = request.json or {}
    try:
        price_str = f"{float(str(data.get('new_price','')).replace(',','.')):.2f}"
    except (ValueError, TypeError):
        return jsonify({'error': 'Preț invalid'}), 400
    resp = shopify_put(f"variants/{data['variant_id']}.json", cfg,
                       {'variant': {'id': data['variant_id'], 'price': price_str}})
    if resp.status_code == 200:
        return jsonify({'status': 'ok', 'new_price': resp.json().get('variant', {}).get('price', price_str)})
    return jsonify({'error': f'Eroare Shopify {resp.status_code}', 'details': resp.text[:300]}), 400


@app.route('/api/bulk-update', methods=['POST'])
def bulk_update():
    cfg = load_config()
    if not cfg.get('access_token'):
        return jsonify({'error': 'Neconectat'}), 400
    updates = request.json or []
    results = []
    for item in updates:
        try:
            price_str = f"{float(str(item.get('new_price','')).replace(',','.')):.2f}"
        except (ValueError, TypeError):
            results.append({'variant_id': item.get('variant_id'), 'status': 'error', 'message': 'Preț invalid'})
            continue
        resp = shopify_put(f"variants/{item['variant_id']}.json", cfg,
                           {'variant': {'id': item['variant_id'], 'price': price_str}})
        if resp.status_code == 200:
            results.append({'variant_id': item['variant_id'], 'status': 'ok',
                            'new_price': resp.json().get('variant', {}).get('price', price_str)})
        else:
            results.append({'variant_id': item['variant_id'], 'status': 'error',
                            'message': f'Shopify {resp.status_code}: {resp.text[:100]}'})
    ok = sum(1 for r in results if r['status'] == 'ok')
    return jsonify({'results': results, 'ok': ok, 'errors': len(results) - ok})


# ── Competitors ───────────────────────────────────────────────────────────────

COMPETITORS_FILE = os.path.join(os.path.dirname(__file__), 'competitors.json')

BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'ro-RO,ro;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
}


def load_competitors():
    if os.path.exists(COMPETITORS_FILE):
        with open(COMPETITORS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def save_competitors(data):
    with open(COMPETITORS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def extract_price_from_element(soup_el):
    """
    Extrage prețul dintr-un element BeautifulSoup.
    Gestionează formate speciale (ex: ITGStore cu .units + .sub-units).
    """
    if soup_el is None:
        return None

    # Format special: units + sub-units (ex: ITGStore: <span class="units">490</span><sup class="sub-units">73</sup>)
    units_el = soup_el.select_one('.units')
    sub_el = soup_el.select_one('.sub-units')
    if units_el and sub_el:
        try:
            return float(f"{units_el.get_text().strip()}.{sub_el.get_text().strip()}")
        except ValueError:
            pass

    return extract_price(soup_el.get_text())


def extract_price(text):
    """Extrage primul număr de tip preț dintr-un string."""
    text = text.strip().replace('\xa0', ' ').replace('\u00a0', '').replace(' ', '')
    # Înlocuiește separatoarele românești (1.234,56 → 1234.56)
    match = re.search(r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?)', text)
    if match:
        raw = match.group(1)
        # Detectează formatul: dacă ultimul separator e virgulă cu 2 cifre → zecimal
        if re.search(r',\d{2}$', raw):
            raw = raw.replace('.', '').replace(',', '.')
        else:
            raw = raw.replace(',', '')
        try:
            return float(raw)
        except ValueError:
            pass
    return None


@app.route('/api/competitors', methods=['GET'])
def get_competitors():
    return jsonify(load_competitors())


@app.route('/api/competitors', methods=['POST'])
def save_competitors_route():
    data = request.json or []
    save_competitors(data)
    return jsonify({'status': 'ok'})


@app.route('/api/fetch-competitor-price', methods=['POST'])
def fetch_competitor_price():
    """Preia prețul unui produs de pe un site competitor."""
    if not BS4_AVAILABLE:
        return jsonify({'error': 'beautifulsoup4 nu este instalat. Rulează: pip3 install beautifulsoup4 lxml'}), 500

    data = request.json or {}
    sku = data.get('sku', '').strip()
    competitor_id = data.get('competitor_id', '')

    if not sku:
        return jsonify({'error': 'SKU lipsă'}), 400

    competitors = load_competitors()
    comp = next((c for c in competitors if c.get('id') == competitor_id), None)
    if not comp:
        return jsonify({'error': f'Competitor necunoscut: {competitor_id}'}), 404

    search_url = comp.get('search_url', '').replace('{sku}', requests.utils.quote(sku))
    price_selector = comp.get('price_selector', '')

    if not search_url:
        return jsonify({'error': 'search_url lipsă pentru acest competitor'}), 400

    try:
        resp = requests.get(search_url, headers=BROWSER_HEADERS, timeout=15, allow_redirects=True)
        if resp.status_code != 200:
            return jsonify({'error': f'HTTP {resp.status_code} de la {comp["name"]}'}), 400

        soup = BeautifulSoup(resp.text, 'lxml')

        price = None
        if price_selector:
            el = soup.select_one(price_selector)
            if el:
                price = extract_price_from_element(el)

        # Fallback: caută pattern-uri comune de preț în pagină
        if price is None:
            for selector in [
                '[class*="price"]', '[itemprop="price"]',
                '[class*="pret"]', '[class*="cost"]'
            ]:
                el = soup.select_one(selector)
                if el:
                    candidate = extract_price_from_element(el)
                    if candidate and candidate > 0:
                        price = candidate
                        break

        if price is not None:
            return jsonify({'price': f'{price:.2f}', 'url': search_url, 'competitor': comp['name']})
        else:
            return jsonify({'error': 'Prețul nu a putut fi extras. Verificați selectorul CSS.',
                            'url': search_url}), 404

    except requests.Timeout:
        return jsonify({'error': f'Timeout la {comp["name"]}'}), 408
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/fetch-competitor-prices-bulk', methods=['POST'])
def fetch_competitor_prices_bulk():
    """Preia prețurile pentru mai multe SKU-uri simultan."""
    if not BS4_AVAILABLE:
        return jsonify({'error': 'beautifulsoup4 nu este instalat'}), 500

    data = request.json or {}
    items = data.get('items', [])   # [{variant_id, sku, competitor_id}, ...]
    results = {}

    for item in items:
        sku = item.get('sku', '').strip()
        competitor_id = item.get('competitor_id', '')
        variant_id = item.get('variant_id')
        key = f"{variant_id}_{competitor_id}"

        if not sku:
            results[key] = {'error': 'SKU lipsă'}
            continue

        competitors = load_competitors()
        comp = next((c for c in competitors if c.get('id') == competitor_id), None)
        if not comp:
            results[key] = {'error': 'Competitor necunoscut'}
            continue

        search_url = comp.get('search_url', '').replace('{sku}', requests.utils.quote(sku))
        price_selector = comp.get('price_selector', '')

        try:
            resp = requests.get(search_url, headers=BROWSER_HEADERS, timeout=12, allow_redirects=True)
            if resp.status_code != 200:
                results[key] = {'error': f'HTTP {resp.status_code}'}
                continue

            soup = BeautifulSoup(resp.text, 'lxml')
            price = None

            if price_selector:
                el = soup.select_one(price_selector)
                if el:
                    price = extract_price_from_element(el)

            if price is None:
                for selector in ['[class*="price"]', '[itemprop="price"]', '[class*="pret"]']:
                    el = soup.select_one(selector)
                    if el:
                        candidate = extract_price_from_element(el)
                        if candidate and candidate > 0:
                            price = candidate
                            break

            if price is not None:
                results[key] = {'price': f'{price:.2f}', 'url': search_url}
            else:
                results[key] = {'error': 'Preț negăsit', 'url': search_url}

        except Exception as e:
            results[key] = {'error': str(e)[:80]}

    return jsonify(results)


if __name__ == '__main__':
    print("=" * 60)
    print("  elogicode.ro – Instrument Actualizare Prețuri")
    print("  Deschide: http://127.0.0.1:5000")
    print("=" * 60)
    app.run(debug=False, host='127.0.0.1', port=5000)
