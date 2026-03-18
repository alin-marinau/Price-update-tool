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


if __name__ == '__main__':
    print("=" * 60)
    print("  elogicode.ro – Instrument Actualizare Prețuri")
    print("  Deschide: http://127.0.0.1:5000")
    print("=" * 60)
    app.run(debug=False, host='127.0.0.1', port=5000)
