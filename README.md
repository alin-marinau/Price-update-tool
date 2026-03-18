# elogicode.ro – Instrument Actualizare Prețuri Shopify

Aplicație web locală pentru actualizarea rapidă a prețurilor produselor din magazinul Shopify.

---

## Cerințe

- Python 3.8+
- Pip

---

## Instalare

```bash
# 1. Intră în folderul aplicației
cd shopify-pricetool

# 2. Instalează dependențele
pip install -r requirements.txt

# 3. Pornește serverul
python app.py
```

Deschide browserul la: **http://127.0.0.1:5000**

---

## Configurare Shopify Admin API Token

1. Intră în **Shopify Admin** → *Settings → Apps and sales channels*
2. Click **Develop apps** → **Create an app** (ex: `Price Tool`)
3. Mergi la **Configuration** → **Admin API scopes**
4. Activează: `read_products`, `write_products`
5. Salvează → **Install app**
6. Copiază **Admin API access token** *(se afișează o singură dată!)*

---

## Utilizare

1. La prima utilizare, introdu **Store URL** și **Access Token** în panoul de configurare
2. Apasă **Salvează & Conectează**
3. Apasă **Încarcă produse** – aplicația va descărca toate produsele din Shopify
4. Produsele sunt grupate pe **categorii** (colecții Shopify)
5. Fiecare rând afișează: Denumire | SKU | Preț curent | **Preț nou**
6. Completează câmpul **Preț nou** pentru produsele pe care dorești să le modifici
   - Rândul se va evidenția în portocaliu
   - Poți salva individual (butonul ✓ de pe rând) sau în masă
7. Apasă **Salvează modificările** din bara de jos pentru a actualiza toate prețurile simultan

---

## Note de securitate

- Tokenul API este salvat local în `config.json` (nu îl distribui)
- Adaugă `config.json` în `.gitignore` dacă folosești Git
- Aplicația rulează **doar local** (127.0.0.1)

---

## Structura fișierelor

```
shopify-pricetool/
├── app.py              ← Backend Flask + proxy Shopify API
├── requirements.txt    ← Dependențe Python
├── config.json         ← Configurație (creat automat)
├── README.md           ← Documentație
└── templates/
    └── index.html      ← Interfața web
```
