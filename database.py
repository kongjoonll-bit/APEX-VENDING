import sqlite3
import os
import json
import time
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'vending.db')

# ============ DEFAULT PRODUCTS (초기화 대비 시드) ============
# Render 무료 플랜은 재배포 때 디스크가 초기화되어 data/vending.db 가 사라진다.
# 부팅 시 seed_default_products() 가 "없는 기본 상품"만 다시 만들어 준다.
# (이름, 가격, 설명)
DEFAULT_PRODUCTS = [
    ('로블랜덤쿠키', 550, '로블록스 랜덤쿠키', '랜덤쿠키'),
    ('입양쿠키', 1200, '입양하세요를 플레이한적이 있는 계정의 쿠키', '게임쿠키'),
    ('블레이드볼쿠키', 1200, '블레이드볼를 플레이한적이 있는 계정의 쿠키', '게임쿠키'),
    ('블피쿠키', 1200, '블록스피스를 플레이한적이 있는 계정의 쿠키', '게임쿠키'),
    ('브훔쿠키', 1500, '브레인로트 훔치기를 플레이한적이 있는 계정의 쿠키', '게임쿠키'),
    ('리미티드쿠키', 2000, '리미티드가 있는 계정의 쿠키', '리미티드쿠키'),
    ('랜덤로벅쿠키', 1000, '랜덤로벅스가 들어있는 계정의 쿠키', '로벅쿠키'),
    ('벌시물쿠키', 3000, '벌시뮬을 플레이한적이 있는 계정의 쿠키', '게임쿠키'),
    ('배구전설쿠키', 3000, '배구전설을 플레이한적이 있는 계정의 쿠키', '게임쿠키'),
    ('입양겜패쿠키', 3000, '입양하세요의 게임패스가 있는 계정의 쿠키', '게임패스쿠키'),
    ('머더미스테리 겜패쿠키', 3000, '머더 미스테리 게임패스가 있는 계정의 쿠키', '게임패스쿠키'),
    ('1만로벅이상사용 쿠키', 1500, '10000로벅 이상 사용한 계정의 쿠키', '로벅스사용쿠키'),
    ('3만로벅이상사용 쿠키', 4000, '30000로벅 이상 사용한 계정의 쿠키', '로벅스사용쿠키'),
    ('5만로벅이상사용 쿠키', 6000, '50000로벅 이상 사용한 계정의 쿠키 (레전드쿠키일 확률 가장높음)', '로벅스사용쿠키'),
    ('50로벅 이상 쿠키', 2500, '50로벅 이상 있는계정 쿠키', '로벅쿠키'),
    ('100로벅 이상 쿠키', 3500, '100로벅 이상 있는계정 쿠키', '로벅쿠키'),
    ('200로벅 이상 쿠키', 7000, '200로벅 이상 있는계정 쿠키', '로벅쿠키'),
    ('500로벅 이상 쿠키', 15000, '500로벅 이상 있는계정 쿠키, 아주 좋은 계정일 확률이 매우높음', '로벅쿠키'),
    ('라이벌쿠키', 3500, '라이벌에서 250로벅 이상 사용쿠키', '게임쿠키'),
    ('라이벌쿠키', 5000, '라이벌에서 1000로벅 이상 사용쿠키', '게임쿠키'),
    ('입양쿠키', 8000, '입양하세요에서 5000로벅 이상 사용쿠키', '게임쿠키'),
]

# ============ DEFAULT SETTINGS (초기화 대비 시드) ============
# DB 가 초기화되어도 채널 ID/운영 설정이 유지되도록, "없는 키"만 기본값으로 채운다.
# (대시보드에서 값을 바꾸면 그 값이 우선이며, 덮어쓰지 않는다)
DEFAULT_SETTINGS = {
    'bot_name': 'APEX VENDING',
    'dashboard_url': 'https://apex-vending.onrender.com',
    'admin_password': 'zizer731!!',
    'admin_channel_id': '1569312425772318750',
    'purchase_log_channel_id': '1537817248457170964',
    'deposit_log_channel_id': '1538129263792754809',
    'charge_log_channel_id': '1543260455500521573',
    'stock_channel_id': '1537817166819106827',
    'notice_channel_id': '1538705204948631652',
    'purchase_role_id': '1538126406662225981',
    'review_channel_id': '1537817307475349554',
    'ticket_category_id': '1538518399066308668',
    'use_categories': 'true',
    'card_image_enabled': 'true',
    'cookie_check_enabled': 'true',
    'cookie_check_minutes': '3',
    'cookie_max_age_minutes': '10',
    'charge_expire_minutes': '5',
    'deposit_webhook_key': '071763f7a8c9b6e37efef24be2fdb5e9',
}

def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()
    
    # Settings table
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')
    
    # Products table
    c.execute('''CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        price INTEGER NOT NULL,
        description TEXT DEFAULT '',
        stock INTEGER DEFAULT 0,
        active INTEGER DEFAULT 1,
        category TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Add category column if not exists (migration for existing DBs)
    try:
        c.execute('ALTER TABLE products ADD COLUMN category TEXT DEFAULT \'\'')
    except:
        pass  # column already exists
    
    # Keys table (텍스트 키 + 파일 재고 지원)
    c.execute('''CREATE TABLE IF NOT EXISTS keys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        key_value TEXT NOT NULL DEFAULT '',
        used INTEGER DEFAULT 0,
        order_id INTEGER DEFAULT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        file_name TEXT DEFAULT '',
        file_data BLOB,
        file_size INTEGER DEFAULT 0,
        invalid INTEGER DEFAULT 0,
        cookie_valid INTEGER DEFAULT NULL,
        cookie_username TEXT DEFAULT '',
        cookie_user_id TEXT DEFAULT '',
        cookie_checked_at TEXT DEFAULT NULL,
        cookie_error TEXT DEFAULT '',
        FOREIGN KEY (product_id) REFERENCES products(id)
    )''')

    # 기존 DB 마이그레이션: 파일 재고 + 쿠키 검사 컬럼 보장
    for _col in ('file_name TEXT DEFAULT \'\'', 'file_data BLOB', 'file_size INTEGER DEFAULT 0',
                 'invalid INTEGER DEFAULT 0', 'cookie_valid INTEGER DEFAULT NULL',
                 'cookie_username TEXT DEFAULT \'\'', 'cookie_user_id TEXT DEFAULT \'\'',
                 'cookie_checked_at TEXT DEFAULT NULL', 'cookie_error TEXT DEFAULT \'\''):
        try:
            c.execute(f'ALTER TABLE keys ADD COLUMN {_col}')
        except Exception:
            pass  # 이미 존재
    
    # Orders table
    c.execute('''CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        username TEXT NOT NULL,
        product_id INTEGER NOT NULL,
        product_name TEXT NOT NULL,
        amount INTEGER NOT NULL,
        status TEXT DEFAULT 'pending',  -- pending, confirmed, cancelled, completed
        key_id INTEGER DEFAULT NULL,
        reviewed INTEGER DEFAULT 0,  -- 후기 작성 여부 (구매당 1개 제한)
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        confirmed_at TEXT DEFAULT NULL,
        FOREIGN KEY (product_id) REFERENCES products(id)
    )''')

    # 기존 DB 마이그레이션: 후기 작성 여부 컬럼 보장
    try:
        c.execute("ALTER TABLE orders ADD COLUMN reviewed INTEGER DEFAULT 0")
    except Exception:
        pass  # 이미 존재
    
    # Admins table
    c.execute('''CREATE TABLE IF NOT EXISTS admins (
        user_id TEXT PRIMARY KEY,
        username TEXT NOT NULL
    )''')
    
    # Users table (for balance/points)
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        username TEXT NOT NULL,
        balance INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Transactions table
    c.execute('''CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        amount INTEGER NOT NULL,
        type TEXT NOT NULL,  -- charge, purchase, admin_add, admin_remove
        description TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Charge requests table (for deposit matching)
    c.execute('''CREATE TABLE IF NOT EXISTS charge_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        username TEXT NOT NULL,
        depositor_name TEXT NOT NULL,
        amount INTEGER NOT NULL,
        status TEXT DEFAULT 'pending',  -- pending, completed, cancelled
        receipt_image_url TEXT DEFAULT '',  -- 수동 승인용 입금 스크린샷 첨부 이미지 URL
        decided_by TEXT DEFAULT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        completed_at TEXT DEFAULT NULL
    )''')

    # 기존 DB 마이그레이션: 증거이미지/결정자/리마인더 발송여부 컬럼 보장
    for _col in ('receipt_image_url TEXT DEFAULT \'\'', 'decided_by TEXT', 'reminder_sent INTEGER DEFAULT 0'):
        try:
            c.execute(f'ALTER TABLE charge_requests ADD COLUMN {_col}')
        except Exception:
            pass  # 이미 존재
    
    # Tickets table (for inquiry/support system)
    c.execute('''CREATE TABLE IF NOT EXISTS tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        username TEXT NOT NULL,
        channel_id TEXT NOT NULL,
        status TEXT DEFAULT 'open',  -- open, closed
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        closed_at TEXT DEFAULT NULL
    )''')
    
    # Coupons table (할인 쿠폰/이벤트)
    c.execute('''CREATE TABLE IF NOT EXISTS coupons (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        discount_amount INTEGER NOT NULL,
        max_uses INTEGER DEFAULT 0,  -- 0 = 무제한
        used_count INTEGER DEFAULT 0,
        active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    
    conn.commit()
    conn.close()

    # DB 가 초기화되었거나(디스크 리셋) 기본 상품이 빠졌으면 자동 복원
    try:
        _seeded = seed_default_products()
        if _seeded:
            print(f"[DB] 기본 상품 {_seeded}개 자동 복원 완료")
    except Exception as _e:
        print(f"[DB] 기본 상품 시드 건너뜀: {_e}")

# ============ SETTINGS ============
def get_setting(key, default=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT value FROM settings WHERE key=?', (key,))
    row = c.fetchone()
    conn.close()
    if row:
        return row['value']
    return default

def set_setting(key, value):
    conn = get_conn()
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, str(value)))
    conn.commit()
    conn.close()

def get_all_settings():
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT * FROM settings')
    rows = c.fetchall()
    conn.close()
    return {row['key']: row['value'] for row in rows}

# ============ PRODUCTS ============
def seed_default_products(force=False):
    """기본 상품(DEFAULT_PRODUCTS) + 기본 설정(DEFAULT_SETTINGS)을 DB에 보장한다.

    - 상품: (이름, 가격, 설명) 조합으로 존재 여부를 판단 → 같은 이름이라도
      가격/설명이 다르면 별도 상품으로 추가된다.
    - 설정: "없는 키"만 기본값으로 채운다 (기존 값은 절대 덮어쓰지 않음).
    - 'default_products_seeded' 플래그로 판단하여, 사용자가 관리자 화면에서
      직접 삭제한 상품은 다음 부팅때 되살리지 않는다.
    - force=True 이면 플래그와 무관하게 빠진 기본 상품을 채운다.

    Returns: 새로 추가된 상품 수
    """
    inserted = 0
    try:
        conn = get_conn()
        c = conn.cursor()

        # --- 기본 설정 시드 (없는 키만) ---
        c.execute('SELECT key FROM settings')
        have = {row['key'] for row in c.fetchall()}
        for _k, _v in DEFAULT_SETTINGS.items():
            if _k not in have:
                c.execute('INSERT INTO settings (key, value) VALUES (?, ?)', (_k, str(_v)))

        c.execute('SELECT name, price, description FROM products')
        existing = {(row['name'], int(row['price'] or 0), (row['description'] or '')) for row in c.fetchall()}
        c.execute('SELECT COUNT(*) AS n FROM products')
        total = c.fetchone()['n']

        # 카테고리 백필: 기존에 만들어진 기본 상품 중 카테고리가 비어있는 것만 채운다
        for name, price, description, category in DEFAULT_PRODUCTS:
            if category:
                c.execute(
                    "UPDATE products SET category=? WHERE name=? AND (category IS NULL OR TRIM(category)='')",
                    (category, name)
                )

        # 카테고리 정정 마이그레이션(v2): 1만/3만/5만 → '로벅스사용쿠키' (1회)
        c.execute("SELECT value FROM settings WHERE key='category_migration_v2'")
        if not c.fetchone():
            for _n in ('1만로벅이상사용 쿠키', '3만로벅이상사용 쿠키', '5만로벅이상사용 쿠키'):
                c.execute(
                    "UPDATE products SET category='로벅스사용쿠키' WHERE name=? AND (category IS NULL OR TRIM(category) IN ('', '로벅쿠키'))",
                    (_n,)
                )
            c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('category_migration_v2', '1')")

        c.execute("SELECT value FROM settings WHERE key='default_products_seeded'")
        row = c.fetchone()
        seeded = (row['value'] == '1') if row else False

        # 상품이 남아있고 이미 시드한 DB라면 상품은 건드리지 않는다
        if total > 0 and seeded and not force:
            conn.commit()
            conn.close()
            return 0

        for name, price, description, category in DEFAULT_PRODUCTS:
            if (name, int(price), description) in existing:
                continue
            c.execute(
                'INSERT INTO products (name, price, description, stock, active, category) '
                'VALUES (?, ?, ?, 0, 1, ?)',
                (name, price, description, category)
            )
            inserted += 1

        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('default_products_seeded', '1')")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[DB] seed_default_products 실패: {e}")
        return 0
    return inserted


def add_product(name, price, description='', stock=0, category=''):
    conn = get_conn()
    c = conn.cursor()
    c.execute('INSERT INTO products (name, price, description, stock, category) VALUES (?, ?, ?, ?, ?)',
              (name, price, description, stock, category))
    conn.commit()
    pid = c.lastrowid
    conn.close()
    return pid

def get_products(active_only=False):
    conn = get_conn()
    c = conn.cursor()
    if active_only:
        c.execute('SELECT * FROM products WHERE active=1 ORDER BY id')
    else:
        c.execute('SELECT * FROM products ORDER BY id')
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_categories():
    """Get all product categories (non-empty, unique)"""
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT DISTINCT category FROM products WHERE category != '' ORDER BY category")
    rows = c.fetchall()
    conn.close()
    return [r['category'] for r in rows if r['category']]

def get_products_by_category(category, active_only=False):
    """Get products filtered by category"""
    conn = get_conn()
    c = conn.cursor()
    if active_only:
        c.execute('SELECT * FROM products WHERE active=1 AND category=? ORDER BY id', (category,))
    else:
        c.execute('SELECT * FROM products WHERE category=? ORDER BY id', (category,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_product(pid):
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT * FROM products WHERE id=?', (pid,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def update_product(pid, name=None, price=None, description=None, stock=None, active=None, category=None):
    conn = get_conn()
    c = conn.cursor()
    product = get_product(pid)
    if not product:
        conn.close()
        return False
    if name is not None: product['name'] = name
    if price is not None: product['price'] = price
    if description is not None: product['description'] = description
    if stock is not None: product['stock'] = stock
    if active is not None: product['active'] = active
    if category is not None: product['category'] = category
    c.execute('UPDATE products SET name=?, price=?, description=?, stock=?, active=?, category=? WHERE id=?',
              (product['name'], product['price'], product['description'], product['stock'], product['active'], product['category'], pid))
    conn.commit()
    conn.close()
    return True

def delete_product(pid):
    conn = get_conn()
    c = conn.cursor()
    c.execute('DELETE FROM products WHERE id=?', (pid,))
    c.execute('DELETE FROM keys WHERE product_id=?', (pid,))
    conn.commit()
    conn.close()

# ============ KEYS ============
def add_keys(product_id, key_list):
    """텍스트 키 여러 개 등록 → 등록된 개수 반환"""
    conn = get_conn()
    c = conn.cursor()
    count = 0
    for k in key_list:
        k = (k or '').strip()
        if not k:
            continue
        c.execute('INSERT INTO keys (product_id, key_value) VALUES (?, ?)', (product_id, k))
        count += 1
    conn.commit()
    conn.close()
    return count

def add_key_files(product_id, files):
    """파일(txt 등)을 재고로 등록 → 등록된 개수 반환

    files: [(filename, bytes), ...] 형태
    파일 1개 = 재고 1개이며, 구매 시 해당 파일이 DM 첨부파일로 전송됩니다.
    """
    if not files:
        return 0
    conn = get_conn()
    c = conn.cursor()
    count = 0
    for item in files:
        try:
            name, data = item
        except (TypeError, ValueError):
            continue
        if not data:
            continue
        name = (name or '').strip() or 'file.txt'
        c.execute(
            'INSERT INTO keys (product_id, key_value, file_name, file_data, file_size) '
            'VALUES (?, ?, ?, ?, ?)',
            (product_id, '', name, sqlite3.Binary(data), len(data))
        )
        count += 1
    conn.commit()
    conn.close()
    return count

def get_key_file(key_id):
    """재고(키)에 첨부된 파일 반환 → (file_name, bytes) 또는 None"""
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT file_name, file_data FROM keys WHERE id=?', (key_id,))
    row = c.fetchone()
    conn.close()
    if not row or not row['file_data']:
        return None
    return (row['file_name'] or 'file.txt'), bytes(row['file_data'])

def get_available_key(product_id):
    """판매 가능한 재고 1개 반환

    - 텍스트 키: 그대로 판매
    - 파일 재고: 쿠키 검사를 최근(기본 10분 이내) 통과한 것만 판매
      → 검사가 끝나지 않았거나 오래된(만료 가능) 파일은 절대 지급하지 않는다.
    """
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        'SELECT * FROM keys WHERE product_id=? AND used=0 AND IFNULL(invalid, 0)=0 '
        'AND (IFNULL(file_size, 0)=0 OR (cookie_checked_at IS NOT NULL '
        '     AND cookie_checked_at >= datetime(\'now\', ?))) '
        'ORDER BY id LIMIT 1',
        (product_id, '-%d minutes' % cookie_max_age_minutes())
    )
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def get_keys(product_id=None, used=None):
    """재고 목록 조회 (파일 원본 BLOB 제외, 쿠키/판매가능 여부 포함)"""
    conn = get_conn()
    c = conn.cursor()
    columns = ("id, product_id, key_value, used, order_id, created_at, file_name, file_size, "
               "IFNULL(invalid, 0) AS invalid, cookie_valid, cookie_username, cookie_user_id, "
               "cookie_checked_at, cookie_error, "
               "CASE WHEN IFNULL(file_size, 0) > 0 THEN 1 ELSE 0 END AS is_file, "
               "CASE WHEN used=0 AND IFNULL(invalid, 0)=0 "
               "          AND (IFNULL(file_size, 0)=0 OR (cookie_checked_at IS NOT NULL "
               "               AND cookie_checked_at >= datetime('now', ?))) "
               "     THEN 1 ELSE 0 END AS sellable")
    params = ['-%d minutes' % cookie_max_age_minutes()]
    query = 'SELECT %s FROM keys' % columns
    where = []
    if product_id:
        where.append('product_id=?')
        params.append(product_id)
    if used is not None:
        where.append('used=?')
        params.append(used)
    if where:
        query += ' WHERE ' + ' AND '.join(where)
    query += ' ORDER BY id DESC'
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def delete_key(key_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute('DELETE FROM keys WHERE id=?', (key_id,))
    conn.commit()
    conn.close()

def count_available_keys(product_id):
    """판매 가능한 재고 수 (만료/미검사 파일은 제외)"""
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        'SELECT COUNT(*) as cnt FROM keys WHERE product_id=? AND used=0 AND IFNULL(invalid, 0)=0 '
        'AND (IFNULL(file_size, 0)=0 OR (cookie_checked_at IS NOT NULL '
        '     AND cookie_checked_at >= datetime(\'now\', ?)))',
        (product_id, '-%d minutes' % cookie_max_age_minutes())
    )
    row = c.fetchone()
    conn.close()
    return row['cnt'] if row else 0

# ============ 로블록스 쿠키 검사 ============
_COOKIE_AGE_CACHE = {'ts': 0.0, 'minutes': 10}

def cookie_max_age_minutes():
    """쿠키 재고 판매 허용 최대 경과 시간(분)

    검사 이력이 이 시간보다 오래된 파일 재고는 '만료 가능'으로 보고 판매하지 않는다.
    (기본 10분, 설정값 cookie_max_age_minutes)
    """
    now = time.time()
    if now - _COOKIE_AGE_CACHE['ts'] < 60:
        return _COOKIE_AGE_CACHE['minutes']
    # 자동 검사를 끈 경우에는 시간 제한을 사실상 해제 (검사 개념 자체가 없으므로)
    try:
        if str(get_setting('cookie_check_enabled', 'true')).strip().lower() == 'false':
            _COOKIE_AGE_CACHE['ts'] = now
            _COOKIE_AGE_CACHE['minutes'] = 5256000  # 약 10년
            return 5256000
    except Exception:
        pass
    try:
        minutes = int(str(get_setting('cookie_max_age_minutes', '') or 10).strip())
    except (TypeError, ValueError):
        minutes = 10
    minutes = max(1, min(minutes, 1440))
    _COOKIE_AGE_CACHE['ts'] = now
    _COOKIE_AGE_CACHE['minutes'] = minutes
    return minutes
def get_unused_file_keys(limit=80, product_id=None):
    """검사 대상: 미사용 파일 재고 (파일 원본 포함)"""
    conn = get_conn()
    c = conn.cursor()
    query = ('SELECT id, product_id, file_name, file_size, file_data, invalid, '
             'cookie_valid, cookie_username, cookie_checked_at, cookie_error '
             'FROM keys WHERE used=0 AND IFNULL(file_size, 0) > 0')
    params = []
    if product_id:
        query += ' AND product_id=?'
        params.append(product_id)
    query += ' ORDER BY (cookie_checked_at IS NULL) DESC, cookie_checked_at ASC, id ASC LIMIT ?'
    params.append(int(limit))
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def set_key_cookie_status(key_id, valid, username='', user_id='', error='', not_cookie=False, touch_time=True):
    """쿠키 검사 결과 저장

    valid=True  → 판매 가능(invalid=0), 검사시각 갱신
    valid=False → 판매 중지(invalid=1), 검사시각 갱신
    valid=None  → 판단 불가
        · not_cookie=True(쿠키 파일 아님) → 검사시각 갱신(판매 가능 유지)
        · 그 외(네트워크/서버 오류)      → 검사시각을 갱신하지 않음
          → 일정 시간이 지나면 '만료 위험'으로 판매가 자동 보류된다.
    """
    conn = get_conn()
    c = conn.cursor()
    if valid is True:
        c.execute('''UPDATE keys SET cookie_valid=1, cookie_username=?, cookie_user_id=?,
                     cookie_error='', cookie_checked_at=CURRENT_TIMESTAMP, invalid=0
                     WHERE id=?''', (username or '', user_id or '', key_id))
    elif valid is False:
        c.execute('''UPDATE keys SET cookie_valid=0, cookie_username=?, cookie_user_id=?,
                     cookie_error=?, cookie_checked_at=CURRENT_TIMESTAMP, invalid=1
                     WHERE id=?''', (username or '', user_id or '', error or '쿠키 무효', key_id))
    elif not_cookie or touch_time:
        c.execute('''UPDATE keys SET cookie_error=?, cookie_checked_at=CURRENT_TIMESTAMP
                     WHERE id=?''', (error or '검사 불가', key_id))
    else:
        c.execute('UPDATE keys SET cookie_error=? WHERE id=?', (error or '검사 불가', key_id))
    conn.commit()
    conn.close()

def set_key_invalid(key_id, invalid=True):
    """재고 판매 가능/불가 수동 전환"""
    conn = get_conn()
    c = conn.cursor()
    c.execute('UPDATE keys SET invalid=? WHERE id=?', (1 if invalid else 0, key_id))
    conn.commit()
    conn.close()

def count_cookie_status(product_id=None):
    """쿠키 재고 현황 집계 (미사용 파일 재고 기준)"""
    conn = get_conn()
    c = conn.cursor()
    query = ('SELECT COUNT(*) AS total, '
             'SUM(CASE WHEN IFNULL(invalid,0)=1 THEN 1 ELSE 0 END) AS invalid, '
             'SUM(CASE WHEN IFNULL(cookie_valid,1)=1 AND IFNULL(invalid,0)=0 THEN 1 ELSE 0 END) AS valid, '
             'SUM(CASE WHEN cookie_valid IS NULL THEN 1 ELSE 0 END) AS unchecked, '
             'SUM(CASE WHEN IFNULL(invalid,0)=0 AND cookie_checked_at IS NOT NULL '
             '         AND cookie_checked_at >= datetime(\'now\', ?) THEN 1 ELSE 0 END) AS sellable '
             'FROM keys WHERE used=0 AND IFNULL(file_size, 0) > 0')
    params = ['-%d minutes' % cookie_max_age_minutes()]
    if product_id:
        query += ' AND product_id=?'
        params.append(product_id)
    c.execute(query, params)
    row = c.fetchone()
    conn.close()
    if not row:
        return {'total': 0, 'invalid': 0, 'valid': 0, 'unchecked': 0, 'sellable': 0}
    return {
        'total': row['total'] or 0,
        'invalid': row['invalid'] or 0,
        'valid': row['valid'] or 0,
        'unchecked': row['unchecked'] or 0,
        'sellable': row['sellable'] or 0,
    }

# ============ ORDERS ============
def create_order(user_id, username, product_id, product_name, amount):
    conn = get_conn()
    c = conn.cursor()
    c.execute('''INSERT INTO orders (user_id, username, product_id, product_name, amount, status)
                 VALUES (?, ?, ?, ?, ?, 'pending')''',
              (user_id, username, product_id, product_name, amount))
    conn.commit()
    oid = c.lastrowid
    conn.close()
    return oid

def get_order(oid):
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT * FROM orders WHERE id=?', (oid,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def order_is_reviewed(oid):
    """해당 주문의 후기 작성 여부 확인 (1이면 이미 작성함)"""
    row = get_order(oid)
    if not row:
        return None
    return bool(row.get('reviewed', 0))

def mark_order_reviewed(oid):
    """해당 주문에 리뷰가 작성되었음을 기록"""
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE orders SET reviewed=1 WHERE id=?", (oid,))
    conn.commit()
    conn.close()

def has_recent_order(user_id, minutes=30):
    """최근 N분 이내에 구매(완료/확정)한 주문이 있는지 — 불량교환 티켓 자격 확인용"""
    try:
        conn = get_conn()
        c = conn.cursor()
        c.execute(
            "SELECT id, product_name, created_at FROM orders "
            "WHERE user_id=? AND status IN ('confirmed','completed') "
            "AND created_at >= datetime('now', ?) "
            "ORDER BY id DESC LIMIT 1",
            (str(user_id), f'-{int(minutes)} minutes')
        )
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception:
        return None


def get_orders(status=None, user_id=None, limit=100):
    conn = get_conn()
    c = conn.cursor()
    query = 'SELECT * FROM orders'
    conditions = []
    params = []
    if status:
        conditions.append('status=?')
        params.append(status)
    if user_id:
        conditions.append('user_id=?')
        params.append(user_id)
    if conditions:
        query += ' WHERE ' + ' AND '.join(conditions)
    query += ' ORDER BY id DESC LIMIT ?'
    params.append(limit)
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_order_with_key(order_id):
    """주문과 함께 지급된 키/파일 정보를 조회 (관리자 패널용)"""
    order = get_order(order_id)
    if not order:
        return None
    key_val = None
    key_file_name = None
    key_file_size = 0
    if order.get('key_id'):
        conn = get_conn()
        c = conn.cursor()
        c.execute('SELECT key_value, file_name, file_size FROM keys WHERE id=?', (order['key_id'],))
        row = c.fetchone()
        conn.close()
        if row:
            key_val = row['key_value']
            key_file_name = row['file_name']
            key_file_size = row['file_size'] or 0
    order['key_value'] = key_val
    order['key_file_name'] = key_file_name
    order['key_file_size'] = key_file_size
    return order

def get_orders_with_keys(status=None, limit=200):
    """주문 목록과 함께 지급된 키/파일 정보를 조회 (관리자 패널용)"""
    conn = get_conn()
    c = conn.cursor()
    query = '''SELECT o.*, k.key_value,
                      k.file_name AS key_file_name, k.file_size AS key_file_size
               FROM orders o 
               LEFT JOIN keys k ON o.key_id = k.id'''
    conditions = []
    params = []
    if status:
        conditions.append('o.status=?')
        params.append(status)
    if conditions:
        query += ' WHERE ' + ' AND '.join(conditions)
    query += ' ORDER BY o.id DESC LIMIT ?'
    params.append(limit)
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_pending_orders():
    return get_orders(status='pending')

def update_order_status(oid, status, key_id=None):
    conn = get_conn()
    c = conn.cursor()
    if key_id is not None:
        c.execute('UPDATE orders SET status=?, key_id=?, confirmed_at=CURRENT_TIMESTAMP WHERE id=?',
                  (status, key_id, oid))
    else:
        c.execute('UPDATE orders SET status=?, confirmed_at=CURRENT_TIMESTAMP WHERE id=?',
                  (status, oid))
    conn.commit()
    conn.close()

def get_order_stats():
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT status, COUNT(*) as cnt FROM orders GROUP BY status')
    rows = c.fetchall()
    conn.close()
    stats = {'pending': 0, 'confirmed': 0, 'cancelled': 0, 'completed': 0}
    for r in rows:
        stats[r['status']] = r['cnt']
    return stats

def get_total_revenue():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COALESCE(SUM(amount), 0) as total FROM orders WHERE status IN ('confirmed', 'completed')")
    row = c.fetchone()
    conn.close()
    return row['total'] if row else 0

# ============ VENDING MACHINE ============
def set_vending_message(channel_id, message_id, content_hash=''):
    """자판기 메시지 위치 저장 (content_hash: 메시지 내용이 안 바뀌면 edit을 생략하기 위한 서명)"""
    conn = get_conn()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS vending_messages (
        channel_id TEXT PRIMARY KEY,
        message_id TEXT NOT NULL,
        content_hash TEXT DEFAULT ''
    )''')
    # 기존 DB에 content_hash 컬럼 추가 (마이그레이션)
    try:
        c.execute("ALTER TABLE vending_messages ADD COLUMN content_hash TEXT DEFAULT ''")
    except Exception:
        pass  # 이미 존재
    c.execute('INSERT OR REPLACE INTO vending_messages (channel_id, message_id, content_hash) VALUES (?, ?, ?)',
              (str(channel_id), str(message_id), content_hash or ''))
    conn.commit()
    conn.close()

def get_vending_message(channel_id):
    """Get vending machine message for a channel"""
    conn = get_conn()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS vending_messages (
        channel_id TEXT PRIMARY KEY,
        message_id TEXT NOT NULL,
        content_hash TEXT DEFAULT ''
    )''')
    try:
        c.execute("ALTER TABLE vending_messages ADD COLUMN content_hash TEXT DEFAULT ''")
    except Exception:
        pass  # 이미 존재
    c.execute('SELECT * FROM vending_messages WHERE channel_id=?', (str(channel_id),))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def get_vending_channels():
    """Get all channels with vending machines"""
    conn = get_conn()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS vending_messages (
        channel_id TEXT PRIMARY KEY,
        message_id TEXT NOT NULL,
        content_hash TEXT DEFAULT ''
    )''')
    try:
        c.execute("ALTER TABLE vending_messages ADD COLUMN content_hash TEXT DEFAULT ''")
    except Exception:
        pass  # 이미 존재
    c.execute('SELECT * FROM vending_messages')
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ============ USERS (POINTS) ============
def get_or_create_user(user_id, username):
    """Get or create a user"""
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE user_id=?', (str(user_id),))
    row = c.fetchone()
    if not row:
        c.execute('INSERT INTO users (user_id, username) VALUES (?, ?)', (str(user_id), username))
        conn.commit()
        c.execute('SELECT * FROM users WHERE user_id=?', (str(user_id),))
        row = c.fetchone()
    conn.close()
    return dict(row)

def get_user(user_id):
    """Get a user"""
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE user_id=?', (str(user_id),))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def get_balance(user_id):
    """Get user balance"""
    user = get_user(user_id)
    return user['balance'] if user else 0

def add_balance(user_id, username, amount, trans_type='admin_add', description=''):
    """Add balance to user"""
    user = get_or_create_user(user_id, username)
    new_balance = user['balance'] + amount
    conn = get_conn()
    c = conn.cursor()
    c.execute('UPDATE users SET balance=?, username=? WHERE user_id=?', (new_balance, username, str(user_id)))
    c.execute('INSERT INTO transactions (user_id, amount, type, description) VALUES (?, ?, ?, ?)',
              (str(user_id), amount, trans_type, description))
    conn.commit()
    conn.close()
    return new_balance

def deduct_balance(user_id, amount, trans_type='purchase', description=''):
    """Deduct balance from user"""
    user = get_user(user_id)
    if not user or user['balance'] < amount:
        return False
    new_balance = user['balance'] - amount
    conn = get_conn()
    c = conn.cursor()
    c.execute('UPDATE users SET balance=? WHERE user_id=?', (new_balance, str(user_id)))
    c.execute('INSERT INTO transactions (user_id, amount, type, description) VALUES (?, ?, ?, ?)',
              (str(user_id), -amount, trans_type, description))
    conn.commit()
    conn.close()
    return True

def add_balance_all(amount, trans_type='admin_add', description=''):
    """모든 등록 유저에게 동일한 포인트 지급 (각 유저별 거래 내역 기록)

    Returns: 지급된 유저 수
    """
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT * FROM users')
    rows = c.fetchall()
    affected = 0
    for row in rows:
        new_balance = row['balance'] + amount
        c.execute('UPDATE users SET balance=? WHERE user_id=?', (new_balance, str(row['user_id'])))
        c.execute('INSERT INTO transactions (user_id, amount, type, description) VALUES (?, ?, ?, ?)',
                  (str(row['user_id']), amount, trans_type, description))
        affected += 1
    conn.commit()
    conn.close()
    return affected

def deduct_balance_all(amount, trans_type='admin_remove', description=''):
    """모든 등록 유저에게서 동일한 포인트 차감 (잔액이 0 미만으로는 내려가지 않음)

    Returns: (차감된 유저 수, 실제 총 차감 포인트)
    """
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT * FROM users')
    rows = c.fetchall()
    affected = 0
    total_deducted = 0
    for row in rows:
        deducted = min(amount, row['balance'])
        if deducted <= 0:
            continue
        new_balance = row['balance'] - deducted
        c.execute('UPDATE users SET balance=? WHERE user_id=?', (new_balance, str(row['user_id'])))
        c.execute('INSERT INTO transactions (user_id, amount, type, description) VALUES (?, ?, ?, ?)',
                  (str(row['user_id']), -deducted, trans_type, description))
        affected += 1
        total_deducted += deducted
    conn.commit()
    conn.close()
    return affected, total_deducted

def get_users():
    """Get all users"""
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT * FROM users ORDER BY balance DESC')
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_user_transactions(user_id, limit=20):
    """Get user transactions"""
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT * FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT ?', (str(user_id), limit))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_total_balance():
    """Get total balance across all users"""
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT COALESCE(SUM(balance), 0) as total FROM users')
    row = c.fetchone()
    conn.close()
    return row['total'] if row else 0

# ============ CHARGE REQUESTS ============
def create_charge_request(user_id, username, depositor_name, amount):
    """Create a charge request"""
    conn = get_conn()
    c = conn.cursor()
    c.execute('INSERT INTO charge_requests (user_id, username, depositor_name, amount) VALUES (?, ?, ?, ?)',
              (str(user_id), username, depositor_name, amount))
    conn.commit()
    rid = c.lastrowid
    conn.close()
    return rid

def get_pending_charge_requests():
    """Get all pending charge requests"""
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT * FROM charge_requests WHERE status=? ORDER BY id', ('pending',))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_charge_request(rid):
    """Get a charge request by id"""
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT * FROM charge_requests WHERE id=?', (rid,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def complete_charge_request(rid):
    """Mark a charge request as completed"""
    conn = get_conn()
    c = conn.cursor()
    c.execute('UPDATE charge_requests SET status=?, completed_at=CURRENT_TIMESTAMP WHERE id=?', ('completed', rid))
    conn.commit()
    conn.close()

def cancel_charge_request(rid):
    """Mark a charge request as cancelled"""
    conn = get_conn()
    c = conn.cursor()
    c.execute('UPDATE charge_requests SET status=? WHERE id=?', ('cancelled', rid))
    conn.commit()
    conn.close()

def set_charge_receipt_image(rid, image_url):
    """충전 요청에 입금 증거 스크린샷 이미지 URL 저장"""
    conn = get_conn()
    c = conn.cursor()
    c.execute('UPDATE charge_requests SET receipt_image_url=? WHERE id=?', (image_url, rid))
    conn.commit()
    conn.close()

def get_pending_charge_requests_by_user(user_id):
    """특정 유저의 대기 중인 충전 요청 (가장 오래된 것 우선, 최대 5개)"""
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT * FROM charge_requests WHERE user_id=? AND status=? ORDER BY id ASC LIMIT 5',
              (str(user_id), 'pending'))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_recent_charge_requests(limit=20):
    """최근 충전 요청 목록 (대시보드 진단용, 최신순)"""
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT * FROM charge_requests ORDER BY id DESC LIMIT ?', (int(limit),))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_charge_requests_needing_reminder(minutes=3, expire_minutes=30, limit=20):
    """자동 충전 리마인더가 필요한 대기 충전 요청 조회.

    조건: 아직 pending + 리마인더 미발송 + 신청 후 {minutes}분 경과 + 유효 시간({expire_minutes}분) 이내
    (created_at/completed_at은 SQLite CURRENT_TIMESTAMP = UTC 기준)
    """
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        f"""SELECT * FROM charge_requests
            WHERE status='pending' AND reminder_sent=0
              AND datetime(created_at, '+{int(minutes)} minutes') <= datetime('now')
              AND created_at >= datetime('now', '-{int(expire_minutes)} minutes')
            ORDER BY id ASC LIMIT {int(limit)}"""
    )
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def mark_charge_reminder_sent(rid):
    """충전 요청에 리마인더 DM 발송 완료 표시 (중복 발송 방지)"""
    conn = get_conn()
    c = conn.cursor()
    c.execute('UPDATE charge_requests SET reminder_sent=1 WHERE id=?', (int(rid),))
    conn.commit()
    conn.close()

def get_user_charge_requests(user_id, limit=10):
    """Get charge requests for a user"""
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT * FROM charge_requests WHERE user_id=? ORDER BY id DESC LIMIT ?', (str(user_id), limit))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ============ ADMINS ============
def add_admin(user_id, username):
    conn = get_conn()
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO admins (user_id, username) VALUES (?, ?)', (user_id, username))
    conn.commit()
    conn.close()

def remove_admin(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute('DELETE FROM admins WHERE user_id=?', (user_id,))
    conn.commit()
    conn.close()

def get_admins():
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT * FROM admins')
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def is_admin(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT * FROM admins WHERE user_id=?', (user_id,))
    row = c.fetchone()
    conn.close()
    return row is not None

# ============ TICKETS (INQUIRY SYSTEM) ============
def create_ticket(user_id, username, channel_id):
    """Create a new ticket - only 1 open ticket per user"""
    # Check if user already has an open ticket
    existing = get_open_ticket_by_user(user_id)
    if existing:
        return -1
    
    conn = get_conn()
    c = conn.cursor()
    c.execute('INSERT INTO tickets (user_id, username, channel_id) VALUES (?, ?, ?)',
              (str(user_id), username, str(channel_id)))
    conn.commit()
    tid = c.lastrowid
    conn.close()
    return tid

def get_ticket(tid):
    """Get a ticket by id"""
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT * FROM tickets WHERE id=?', (tid,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def get_ticket_by_channel(channel_id):
    """Get a ticket by channel id"""
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT * FROM tickets WHERE channel_id=?', (str(channel_id),))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def get_open_ticket_by_user(user_id):
    """Get open ticket for a user"""
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT * FROM tickets WHERE user_id=? AND status=?', (str(user_id), 'open'))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def get_open_tickets():
    """Get all open tickets"""
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT * FROM tickets WHERE status=? ORDER BY id', ('open',))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def close_ticket(tid):
    """Close a ticket"""
    conn = get_conn()
    c = conn.cursor()
    c.execute('UPDATE tickets SET status=?, closed_at=CURRENT_TIMESTAMP WHERE id=?', ('closed', tid))
    conn.commit()
    conn.close()

# ============ COUPONS (할인 쿠폰) ============
def create_coupon(code, discount_amount, max_uses=0):
    """쿠폰 생성 - 코드 중복 시 -1 반환"""
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute('INSERT INTO coupons (code, discount_amount, max_uses) VALUES (?, ?, ?)',
                  (code.strip().upper(), int(discount_amount), int(max_uses)))
        conn.commit()
        cid = c.lastrowid
    except sqlite3.IntegrityError:
        cid = -1  # 중복 코드
    conn.close()
    return cid

def get_coupons(active_only=False):
    """쿠폰 목록 조회"""
    conn = get_conn()
    c = conn.cursor()
    if active_only:
        c.execute('SELECT * FROM coupons WHERE active=1 ORDER BY id DESC')
    else:
        c.execute('SELECT * FROM coupons ORDER BY id DESC')
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_coupon(cid):
    """쿠폰 단건 조회"""
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT * FROM coupons WHERE id=?', (cid,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def get_coupon_by_code(code):
    """코드로 쿠폰 조회 (유효성 검사 포함: 활성화 + 사용횟수)"""
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT * FROM coupons WHERE code=?', (str(code).strip().upper(),))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    coupon = dict(row)
    if not coupon['active']:
        return None
    if coupon['max_uses'] > 0 and coupon['used_count'] >= coupon['max_uses']:
        return None
    return coupon

def use_coupon(cid):
    """쿠폰 사용 처리 (사용 횟수 +1)"""
    conn = get_conn()
    c = conn.cursor()
    c.execute('UPDATE coupons SET used_count=used_count+1 WHERE id=?', (cid,))
    conn.commit()
    conn.close()

def delete_coupon(cid):
    """쿠폰 삭제"""
    conn = get_conn()
    c = conn.cursor()
    c.execute('DELETE FROM coupons WHERE id=?', (cid,))
    conn.commit()
    conn.close()

def toggle_coupon(cid):
    """쿠폰 활성화/비활성화 토글"""
    conn = get_conn()
    c = conn.cursor()
    c.execute('UPDATE coupons SET active = CASE WHEN active=1 THEN 0 ELSE 1 END WHERE id=?', (cid,))
    conn.commit()
    conn.close()
