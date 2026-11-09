/* ============================================================
   APEX VENDING · ADMIN CONSOLE SCRIPT
   ============================================================ */
const Apex = {
  async req(url, options = {}) {
    const res = await fetch(url, options);
    let data = null;
    try { data = await res.json(); } catch (e) { data = {}; }
    if (!res.ok) {
      const msg = (data && (data.error || data.message)) || ('요청 실패 (' + res.status + ')');
      throw new Error(msg);
    }
    return data;
  },
  get(url) { return this.req(url); },
  post(url, body) {
    return this.req(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {})
    });
  },
  put(url, body) {
    return this.req(url, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {})
    });
  },
  del(url) { return this.req(url, { method: 'DELETE' }); }
};

const esc = (v) => String(v === null || v === undefined ? '' : v)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;').replace(/'/g, '&#39;');

const fmt = (n) => Number(n || 0).toLocaleString('ko-KR');

const fmtSize = (n) => {
  n = Number(n || 0);
  if (n >= 1048576) return (n / 1048576).toFixed(1) + ' MB';
  if (n >= 1024) return (n / 1024).toFixed(1) + ' KB';
  return n + ' B';
};

/* DB의 UTC 시각 → KST 표시 */
const kst = (value) => {
  if (!value) return '';
  let s = String(value).trim();
  if (s.includes('T') || s.endsWith('Z')) {
    // already ISO
  } else {
    s = s.replace(' ', 'T') + 'Z';
  }
  const d = new Date(s);
  if (isNaN(d.getTime())) return String(value);
  const p = (n) => String(n).padStart(2, '0');
  const parts = new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false
  }).formatToParts(d).reduce((acc, x) => { acc[x.type] = x.value; return acc; }, {});
  return `${parts.year}-${p(parts.month)}-${p(parts.day)} ${p(parts.hour)}:${p(parts.minute)}`;
};

const STATUS_BADGE = {
  pending: 'badge-pending',
  confirmed: 'badge-confirmed',
  completed: 'badge-completed',
  cancelled: 'badge-cancelled'
};

function showToast(message, type = 'success') {
  const toast = document.getElementById('toast');
  if (!toast) return;
  toast.textContent = message;
  toast.className = 'toast ' + type;
  toast.style.display = 'block';
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => { toast.style.display = 'none'; }, 2800);
}

function openModal(id) {
  const m = document.getElementById(id);
  if (m) m.classList.add('active');
}

function closeModal(id) {
  const m = document.getElementById(id);
  if (m) m.classList.remove('active');
}

document.addEventListener('click', (e) => {
  if (e.target && e.target.classList && e.target.classList.contains('modal')) {
    e.target.classList.remove('active');
  }
});

function emptyMessage(colspan, text) {
  return '<tr><td colspan="' + colspan + '" style="text-align:center;color:#8b96a8;padding:20px;">' + esc(text) + '</td></tr>';
}

function loadingMessage(colspan) {
  return emptyMessage(colspan, '불러오는 중...');
}

/* ---------- 탭 전환 ---------- */
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.sidebar nav a[data-tab]').forEach((link) => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      const tab = link.dataset.tab;
      document.querySelectorAll('.sidebar nav a').forEach(a => a.classList.remove('active'));
      link.classList.add('active');
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      const panel = document.getElementById('tab-' + tab);
      if (panel) panel.classList.add('active');

      const loaders = {
        orders: loadOrders,
        keys: loadKeys,
        users: loadUsers,
        coupons: loadCoupons,
        admins: loadAdmins,
        depositlog: loadWebhookLogs
      };
      if (loaders[tab]) loaders[tab]();
    });
  });

  const imageInput = document.getElementById('notice-image');
  if (imageInput) {
    imageInput.addEventListener('change', () => {
      const preview = document.getElementById('notice-image-preview');
      const file = imageInput.files && imageInput.files[0];
      if (!preview) return;
      if (!file) { preview.style.display = 'none'; return; }
      preview.src = URL.createObjectURL(file);
      preview.style.display = 'block';
    });
  }
});

/* ============================================================
   주문 관리
   ============================================================ */
async function loadOrders() {
  const box = document.getElementById('orders-table-container');
  if (!box) return;
  const statusEl = document.getElementById('order-filter');
  const status = statusEl ? statusEl.value : '';
  box.innerHTML = '<p style="color:#8b96a8;text-align:center;padding:20px;">불러오는 중...</p>';
  try {
    const url = '/api/orders?include_keys=true' + (status ? '&status=' + encodeURIComponent(status) : '');
    const orders = await Apex.get(url);
    if (!orders.length) {
      box.innerHTML = '<p style="color:#8b96a8;text-align:center;padding:20px;">주문이 없습니다.</p>';
      return;
    }
    const rows = orders.map((o) => {
      let deliverable = '-';
      if (o.key_file_name) {
        deliverable = '<a href="/api/keys/' + o.key_id + '/download" style="color:#3DDC97;">' +
          esc(o.key_file_name) + '</a><br><small style="opacity:.6;">' + fmtSize(o.key_file_size) + '</small>';
      } else if (o.key_value) {
        deliverable = '<span class="key-value">' + esc(o.key_value) + '</span>';
      }
      let actions = '';
      if (o.status === 'pending') {
        actions = '<button class="btn btn-success btn-sm" onclick="confirmOrder(' + o.id + ')">확인</button> ' +
                  '<button class="btn btn-danger btn-sm" onclick="cancelOrder(' + o.id + ')">취소</button>';
      }
      const badge = STATUS_BADGE[o.status] || '';
      return '<tr>' +
        '<td>#' + o.id + '</td>' +
        '<td>' + esc(o.username) + '</td>' +
        '<td>' + esc(o.product_name) + '</td>' +
        '<td>' + fmt(o.amount) + '원</td>' +
        '<td>' + kst(o.created_at) + '</td>' +
        '<td><span class="badge ' + badge + '">' + esc(o.status) + '</span></td>' +
        '<td>' + deliverable + '</td>' +
        '<td>' + actions + '</td>' +
        '</tr>';
    }).join('');
    box.innerHTML = '<table><thead><tr>' +
      '<th>주문</th><th>구매자</th><th>상품</th><th>금액</th><th>시간</th><th>상태</th><th>지급 내용</th><th>작업</th>' +
      '</tr></thead><tbody>' + rows + '</tbody></table>';
  } catch (err) {
    box.innerHTML = '<p style="color:#FF5C6C;text-align:center;padding:20px;">' + esc(err.message) + '</p>';
  }
}

async function confirmOrder(id) {
  if (!confirm('주문 #' + id + ' 을(를) 확인 처리하고 재고를 DM으로 전송할까요?')) return;
  try {
    const res = await Apex.post('/api/orders/' + id + '/confirm');
    if (res.success) {
      showToast(res.message || '전송 완료');
      loadOrders();
    } else {
      showToast(res.message || '처리에 실패했습니다.', 'error');
    }
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function cancelOrder(id) {
  if (!confirm('주문 #' + id + ' 을(를) 취소할까요?')) return;
  try {
    const res = await Apex.post('/api/orders/' + id + '/cancel');
    if (res.success) {
      showToast(res.message || '취소 완료');
      loadOrders();
    } else {
      showToast(res.message || '취소에 실패했습니다.', 'error');
    }
  } catch (err) {
    showToast(err.message, 'error');
  }
}

/* ============================================================
   상품 관리
   ============================================================ */
let productsCache = [];

async function fetchProducts(force = false) {
  if (!force && productsCache.length) return productsCache;
  productsCache = await Apex.get('/api/products');
  return productsCache;
}

function openProductModal() {
  document.getElementById('product-id').value = '';
  document.getElementById('product-name').value = '';
  document.getElementById('product-price').value = '';
  document.getElementById('product-desc').value = '';
  document.getElementById('product-category').value = '';
  document.getElementById('product-active').value = '1';
  document.getElementById('product-modal-title').textContent = '상품 추가';
  openModal('product-modal');
}

async function editProduct(id) {
  try {
    const products = await fetchProducts(true);
    const p = products.find(x => Number(x.id) === Number(id));
    if (!p) { showToast('상품을 찾을 수 없습니다.', 'error'); return; }
    document.getElementById('product-id').value = p.id;
    document.getElementById('product-name').value = p.name || '';
    document.getElementById('product-price').value = p.price || 0;
    document.getElementById('product-desc').value = p.description || '';
    document.getElementById('product-category').value = p.category || '';
    document.getElementById('product-active').value = String(p.active ? 1 : 0);
    document.getElementById('product-modal-title').textContent = '상품 수정';
    openModal('product-modal');
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function saveProduct() {
  const id = document.getElementById('product-id').value;
  const payload = {
    name: document.getElementById('product-name').value.trim(),
    price: Number(document.getElementById('product-price').value || 0),
    description: document.getElementById('product-desc').value.trim(),
    category: document.getElementById('product-category').value.trim(),
    active: Number(document.getElementById('product-active').value)
  };
  if (!payload.name || payload.price <= 0) {
    showToast('상품명과 가격을 확인해주세요.', 'error');
    return;
  }
  try {
    if (id) {
      await Apex.put('/api/products/' + id, payload);
      showToast('상품이 수정되었습니다.');
    } else {
      await Apex.post('/api/products', payload);
      showToast('상품이 추가되었습니다.');
    }
    closeModal('product-modal');
    productsCache = [];
    setTimeout(() => location.reload(), 700);
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function deleteProduct(id) {
  if (!confirm('상품 #' + id + ' 과(와) 등록된 재고를 모두 삭제할까요?')) return;
  try {
    await Apex.del('/api/products/' + id);
    showToast('상품이 삭제되었습니다.');
    productsCache = [];
    setTimeout(() => location.reload(), 700);
  } catch (err) {
    showToast(err.message, 'error');
  }
}

/* ============================================================
   재고 관리 (텍스트 키 / 파일)
   ============================================================ */
async function loadKeys() {
  const box = document.getElementById('keys-table-container');
  if (!box) return;
  const pidEl = document.getElementById('key-product-filter');
  const usedEl = document.getElementById('key-used-filter');
  const params = [];
  if (pidEl && pidEl.value) params.push('product_id=' + encodeURIComponent(pidEl.value));
  if (usedEl && usedEl.value !== '') params.push('used=' + encodeURIComponent(usedEl.value));

  box.innerHTML = '<p style="color:#8b96a8;text-align:center;padding:20px;">불러오는 중...</p>';
  loadCookieStatus();
  try {
    const keys = await Apex.get('/api/keys' + (params.length ? '?' + params.join('&') : ''));
    if (!keys.length) {
      box.innerHTML = '<p style="color:#8b96a8;text-align:center;padding:20px;">등록된 재고가 없습니다.</p>';
      return;
    }
    const rows = keys.map((k) => {
      const type = k.is_file
        ? '<span class="badge badge-completed">파일</span>'
        : '<span class="badge badge-confirmed">텍스트</span>';
      let value;
      if (k.is_file) {
        value = '<a href="/api/keys/' + k.id + '/download" style="color:#3DDC97;">' +
          esc(k.file_name || 'file') + '</a> <small style="opacity:.6;">' + fmtSize(k.file_size) + '</small>';
      } else {
        value = '<span class="key-value">' + esc(k.key_value) + '</span>';
      }
      const state = k.used
        ? '<span class="badge badge-cancelled">사용됨</span>'
        : '<span class="badge badge-confirmed">미사용</span>';
      const actions = k.is_file
        ? '<button class="btn btn-info btn-sm" onclick="checkCookie(' + k.id + ')">검사</button> ' +
          '<button class="btn btn-danger btn-sm" onclick="deleteKey(' + k.id + ')">삭제</button>'
        : '<button class="btn btn-danger btn-sm" onclick="deleteKey(' + k.id + ')">삭제</button>';
      return '<tr>' +
        '<td>' + k.id + '</td>' +
        '<td>' + k.product_id + '</td>' +
        '<td>' + type + '</td>' +
        '<td>' + value + '</td>' +
        '<td>' + cookieCell(k) + '</td>' +
        '<td>' + state + '</td>' +
        '<td>' + kst(k.created_at) + '</td>' +
        '<td>' + actions + '</td>' +
        '</tr>';
    }).join('');
    box.innerHTML = '<table><thead><tr>' +
      '<th>ID</th><th>상품</th><th>타입</th><th>내용</th><th>쿠키</th><th>상태</th><th>등록일</th><th>작업</th>' +
      '</tr></thead><tbody>' + rows + '</tbody></table>';
  } catch (err) {
    box.innerHTML = '<p style="color:#FF5C6C;text-align:center;padding:20px;">' + esc(err.message) + '</p>';
  }
}

function cookieCell(k) {
  if (!k.is_file) return '-';
  const checked = k.cookie_checked_at
    ? '<div style="font-size:11px;opacity:.55;margin-top:2px;">' + kst(k.cookie_checked_at) + '</div>'
    : '';
  if (Number(k.invalid) === 1 || Number(k.cookie_valid) === 0) {
    const who = k.cookie_username ? ' <b>' + esc(k.cookie_username) + '</b>' : '';
    return '<span class="badge badge-cancelled">무효</span>' + who +
      '<div style="font-size:11px;color:#FF8A95;margin-top:2px;">' + esc(k.cookie_error || '') + '</div>' + checked;
  }
  if (k.cookie_valid === null || k.cookie_valid === undefined) {
    return '<span class="badge badge-pending">미검사</span>' + checked;
  }
  const who = k.cookie_username ? ' <b>' + esc(k.cookie_username) + '</b>' : '';
  if (!Number(k.used) && Number(k.sellable) !== 1) {
    return '<span class="badge badge-pending">판매보류</span>' + who +
      '<div style="font-size:11px;opacity:.7;margin-top:2px;">검사 갱신 필요(만료 위험)</div>' + checked;
  }
  return '<span class="badge badge-confirmed">유효</span>' + who + checked;
}

async function loadCookieStatus() {
  const el = document.getElementById('cookie-status');
  if (!el) return;
  try {
    const s = await Apex.get('/api/cookie-status');
    el.innerHTML = '파일 재고 <b>' + fmt(s.total) + '</b> · 판매가능 <b>' + fmt(s.sellable) +
      '</b> · 유효 <b>' + fmt(s.valid) + '</b> · 무효 <b>' + fmt(s.invalid) +
      '</b> · 미검사 <b>' + fmt(s.unchecked) + '</b>';
  } catch (e) {
    el.textContent = '';
  }
}

async function recheckCookies() {
  try {
    const res = await Apex.post('/api/cookies/recheck');
    showToast(res.message || '쿠키 재검사를 시작했습니다.');
    setTimeout(loadKeys, 4000);
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function checkCookie(id) {
  showToast('쿠키 검사 중...', 'info');
  try {
    const res = await Apex.post('/api/keys/' + id + '/check');
    if (res.valid === true) {
      showToast('유효 · ' + (res.username || '계정 확인') + ' · ' + res.length + '자');
    } else if (res.valid === false) {
      showToast('무효 · ' + (res.error || ''), 'error');
    } else {
      showToast('판단불가 · ' + (res.error || ''), 'error');
    }
    loadKeys();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

function openKeyModal() {
  const ta = document.getElementById('key-values');
  if (ta) ta.value = '';
  openModal('key-modal');
}

async function saveKeys() {
  const pid = document.getElementById('key-product').value;
  const text = document.getElementById('key-values').value;
  const keyList = text.split('\n').map(s => s.trim()).filter(Boolean);
  if (!pid) { showToast('상품을 선택해주세요.', 'error'); return; }
  if (!keyList.length) { showToast('키를 한 개 이상 입력해주세요.', 'error'); return; }
  try {
    const res = await Apex.post('/api/products/' + pid + '/keys', { keys: keyList.join('\n') });
    showToast('키 ' + (res.count || keyList.length) + '개를 등록했습니다.');
    closeModal('key-modal');
    loadKeys();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

function openKeyFileModal() {
  const input = document.getElementById('key-files');
  if (input) input.value = '';
  openModal('key-file-modal');
}

async function saveKeyFiles() {
  const pid = document.getElementById('key-file-product').value;
  const input = document.getElementById('key-files');
  if (!pid) { showToast('상품을 선택해주세요.', 'error'); return; }
  if (!input || !input.files || !input.files.length) {
    showToast('업로드할 파일을 선택해주세요.', 'error');
    return;
  }
  const form = new FormData();
  for (let i = 0; i < input.files.length; i++) form.append('files', input.files[i]);

  try {
    const res = await fetch('/api/products/' + pid + '/keyfiles', { method: 'POST', body: form });
    let data = {};
    try { data = await res.json(); } catch (e) { data = {}; }
    if (!res.ok) throw new Error(data.error || '업로드에 실패했습니다.');

    let msg = '파일 재고 ' + (data.count || 0) + '개를 등록했습니다.';
    if (data.skipped && data.skipped.length) msg += ' (제외 ' + data.skipped.length + '개)';
    showToast(msg);
    closeModal('key-file-modal');
    loadKeys();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function deleteKey(id) {
  if (!confirm('재고 #' + id + ' 을(를) 삭제할까요?')) return;
  try {
    await Apex.del('/api/keys/' + id);
    showToast('삭제되었습니다.');
    loadKeys();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

/* ============================================================
   유저 관리
   ============================================================ */
async function loadUsers() {
  const box = document.getElementById('users-container');
  if (!box) return;
  box.innerHTML = '<p style="color:#8b96a8;text-align:center;padding:20px;">불러오는 중...</p>';
  try {
    const users = await Apex.get('/api/users');
    if (!users.length) {
      box.innerHTML = '<p style="color:#8b96a8;text-align:center;padding:20px;">유저가 없습니다.</p>';
      return;
    }
    const rows = users.map((u) => {
      return '<tr>' +
        '<td><span class="key-value">' + esc(u.user_id) + '</span></td>' +
        '<td>' + esc(u.username) + '</td>' +
        '<td><b>' + fmt(u.balance) + ' P</b></td>' +
        '<td>' + kst(u.created_at) + '</td>' +
        '<td>' +
        '<button class="btn btn-success btn-sm" data-action="add" data-uid="' + esc(u.user_id) +
        '" data-uname="' + esc(u.username) + '">지급</button> ' +
        '<button class="btn btn-danger btn-sm" data-action="deduct" data-uid="' + esc(u.user_id) +
        '" data-uname="' + esc(u.username) + '">차감</button>' +
        '</td></tr>';
    }).join('');
    box.innerHTML = '<table><thead><tr><th>유저 ID</th><th>이름</th><th>보유 포인트</th><th>가입일</th><th>작업</th></tr></thead>' +
      '<tbody>' + rows + '</tbody></table>';

    box.querySelectorAll('button[data-action]').forEach((btn) => {
      btn.addEventListener('click', () => {
        if (btn.dataset.action === 'add') givePoints(btn.dataset.uid, btn.dataset.uname);
        else deductPoints(btn.dataset.uid, btn.dataset.uname);
      });
    });
  } catch (err) {
    box.innerHTML = '<p style="color:#FF5C6C;text-align:center;padding:20px;">' + esc(err.message) + '</p>';
  }
}

async function givePoints(userId, username) {
  const input = prompt(username + ' 님에게 지급할 포인트를 입력하세요.', '1000');
  if (input === null) return;
  const amount = Number(input);
  if (!amount || amount <= 0) { showToast('0보다 큰 숫자를 입력해주세요.', 'error'); return; }
  try {
    const res = await Apex.post('/api/users/' + encodeURIComponent(userId) + '/points',
      { amount: amount, username: username });
    showToast('지급 완료 · 잔액 ' + fmt(res.balance) + ' P');
    loadUsers();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function deductPoints(userId, username) {
  const input = prompt(username + ' 님에게서 차감할 포인트를 입력하세요.', '1000');
  if (input === null) return;
  const amount = Number(input);
  if (!amount || amount <= 0) { showToast('0보다 큰 숫자를 입력해주세요.', 'error'); return; }
  try {
    const res = await Apex.post('/api/users/' + encodeURIComponent(userId) + '/points/deduct',
      { amount: amount });
    showToast('차감 완료 · 잔액 ' + fmt(res.balance) + ' P');
    loadUsers();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

/* ============================================================
   쿠폰 관리
   ============================================================ */
async function saveCoupon() {
  const code = document.getElementById('coupon-code').value.trim();
  const discount = Number(document.getElementById('coupon-discount').value || 0);
  const maxUses = Number(document.getElementById('coupon-max-uses').value || 0);
  if (!code) { showToast('쿠폰 코드를 입력해주세요.', 'error'); return; }
  if (discount <= 0) { showToast('할인 금액을 입력해주세요.', 'error'); return; }
  try {
    await Apex.post('/api/coupons', { code: code, discount_amount: discount, max_uses: maxUses });
    showToast('쿠폰이 생성되었습니다.');
    document.getElementById('coupon-code').value = '';
    document.getElementById('coupon-discount').value = '';
    loadCoupons();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function loadCoupons() {
  const box = document.getElementById('coupons-container');
  if (!box) return;
  box.innerHTML = '<p style="color:#8b96a8;text-align:center;padding:20px;">불러오는 중...</p>';
  try {
    const coupons = await Apex.get('/api/coupons');
    if (!coupons.length) {
      box.innerHTML = '<p style="color:#8b96a8;text-align:center;padding:20px;">생성된 쿠폰이 없습니다.</p>';
      return;
    }
    const rows = coupons.map((c) => {
      const active = Number(c.active) === 1;
      const usage = c.max_uses > 0 ? (c.used_count + ' / ' + c.max_uses) : (c.used_count + ' / 무제한');
      return '<tr>' +
        '<td><span class="key-value">' + esc(c.code) + '</span></td>' +
        '<td>' + fmt(c.discount_amount) + ' P</td>' +
        '<td>' + usage + '</td>' +
        '<td>' + (active ? '<span class="badge badge-confirmed">활성</span>'
                          : '<span class="badge badge-cancelled">중지</span>') + '</td>' +
        '<td>' +
        '<button class="btn btn-warning btn-sm" onclick="toggleCoupon(' + c.id + ')">' +
        (active ? '중지' : '활성') + '</button> ' +
        '<button class="btn btn-danger btn-sm" onclick="deleteCoupon(' + c.id + ')">삭제</button>' +
        '</td></tr>';
    }).join('');
    box.innerHTML = '<table><thead><tr><th>코드</th><th>할인</th><th>사용</th><th>상태</th><th>작업</th></tr></thead>' +
      '<tbody>' + rows + '</tbody></table>';
  } catch (err) {
    box.innerHTML = '<p style="color:#FF5C6C;text-align:center;padding:20px;">' + esc(err.message) + '</p>';
  }
}

async function toggleCoupon(id) {
  try {
    await Apex.post('/api/coupons/' + id + '/toggle');
    loadCoupons();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function deleteCoupon(id) {
  if (!confirm('쿠폰 #' + id + ' 을(를) 삭제할까요?')) return;
  try {
    await Apex.del('/api/coupons/' + id);
    showToast('삭제되었습니다.');
    loadCoupons();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

/* ============================================================
   공지 보내기
   ============================================================ */
async function sendNotice() {
  const title = document.getElementById('notice-title').value.trim();
  const content = document.getElementById('notice-content').value.trim();
  const color = document.getElementById('notice-color').value.trim();
  const imageInput = document.getElementById('notice-image');
  const result = document.getElementById('notice-result');

  if (!title || !content) {
    showToast('제목과 내용을 입력해주세요.', 'error');
    return;
  }

  const form = new FormData();
  form.append('title', title);
  form.append('content', content);
  form.append('color', color);
  if (imageInput && imageInput.files && imageInput.files[0]) {
    form.append('image', imageInput.files[0]);
  }

  if (result) result.innerHTML = '<span style="color:#8b96a8;">전송 중...</span>';
  try {
    const res = await fetch('/api/notice/send', { method: 'POST', body: form });
    const data = await res.json();
    if (!res.ok || !data.success) throw new Error(data.message || data.error || '전송에 실패했습니다.');
    if (result) result.innerHTML = '<span style="color:#3DDC97;">' + esc(data.message || '전송 완료') + '</span>';
    showToast('공지를 전송했습니다.');
  } catch (err) {
    if (result) result.innerHTML = '<span style="color:#FF5C6C;">' + esc(err.message) + '</span>';
    showToast(err.message, 'error');
  }
}

/* ============================================================
   설정
   ============================================================ */
function readValue(id) {
  const el = document.getElementById(id);
  return el ? el.value : '';
}

async function saveSettings() {
  const payload = {
    bot_name: readValue('set-bot-name').trim(),
    discord_token: readValue('set-discord-token').trim(),
    admin_password: readValue('set-admin-password'),
    dashboard_url: readValue('set-dashboard-url').trim(),
    admin_channel_id: readValue('set-admin-channel').trim(),
    purchase_log_channel_id: readValue('set-purchase-log-channel').trim(),
    deposit_log_channel_id: readValue('set-deposit-log-channel').trim(),
    charge_log_channel_id: readValue('set-charge-log-channel').trim(),
    charge_expire_minutes: readValue('set-charge-expire').trim() || '30',
    stock_channel_id: readValue('set-stock-channel').trim(),
    notice_channel_id: readValue('set-notice-channel').trim(),
    purchase_role_id: readValue('set-purchase-role').trim(),
    review_channel_id: readValue('set-review-channel').trim(),
    use_categories: readValue('set-use-categories') || 'false',
    card_image_enabled: readValue('set-card-image') || 'true',
    cookie_check_enabled: readValue('set-cookie-check') || 'true',
    cookie_check_minutes: readValue('set-cookie-minutes').trim() || '3',
    cookie_max_age_minutes: readValue('set-cookie-max-age').trim() || '10',
    vending_footer_channel_id: readValue('set-vending-footer-channel').trim(),
    vending_banner_url: readValue('set-vending-banner').trim()
  };
  try {
    await Apex.post('/api/settings', payload);
    showToast('설정이 저장되었습니다.');
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function saveBankSettings() {
  const payload = {
    bank_name: readValue('set-bank-name').trim(),
    bank_account: readValue('set-bank-account').trim(),
    bank_holder: readValue('set-bank-holder').trim()
  };
  try {
    await Apex.post('/api/settings', payload);
    showToast('입금 계좌가 저장되었습니다.');
  } catch (err) {
    showToast(err.message, 'error');
  }
}

/* ---------- 자판기 하단 배너 이미지 ---------- */
async function uploadBanner() {
  const input = document.getElementById('vending-banner-file');
  if (!input || !input.files || !input.files.length) {
    showToast('이미지를 선택해주세요.', 'error');
    return;
  }
  const form = new FormData();
  form.append('image', input.files[0]);
  try {
    const res = await fetch('/api/vending/banner', { method: 'POST', body: form });
    let data = {};
    try { data = await res.json(); } catch (e) { data = {}; }
    if (!res.ok || !data.success) throw new Error(data.message || '업로드에 실패했습니다.');
    const field = document.getElementById('set-vending-banner');
    if (field) field.value = data.url;
    showToast('배너 이미지가 자판기에 적용되었습니다.');
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function clearBanner() {
  const field = document.getElementById('set-vending-banner');
  if (field) field.value = '';
  try {
    await Apex.post('/api/settings', { vending_banner_url: '' });
    showToast('배너 이미지를 제거했습니다.');
  } catch (err) {
    showToast(err.message, 'error');
  }
}

/* ============================================================
   관리자
   ============================================================ */
async function loadAdmins() {
  const box = document.getElementById('admins-container');
  if (!box) return;
  box.innerHTML = '<p style="color:#8b96a8;text-align:center;padding:20px;">불러오는 중...</p>';
  try {
    const admins = await Apex.get('/api/admins');
    if (!admins.length) {
      box.innerHTML = '<p style="color:#8b96a8;text-align:center;padding:20px;">등록된 관리자가 없습니다.</p>';
      return;
    }
    const rows = admins.map((a) => {
      return '<tr>' +
        '<td><span class="key-value">' + esc(a.user_id) + '</span></td>' +
        '<td>' + esc(a.username) + '</td>' +
        '<td><button class="btn btn-danger btn-sm" data-remove-admin="' + esc(a.user_id) + '">삭제</button></td>' +
        '</tr>';
    }).join('');
    box.innerHTML = '<table><thead><tr><th>유저 ID</th><th>이름</th><th>작업</th></tr></thead>' +
      '<tbody>' + rows + '</tbody></table>';

    box.querySelectorAll('button[data-remove-admin]').forEach((btn) => {
      btn.addEventListener('click', () => removeAdmin(btn.dataset.removeAdmin));
    });
  } catch (err) {
    box.innerHTML = '<p style="color:#FF5C6C;text-align:center;padding:20px;">' + esc(err.message) + '</p>';
  }
}

async function addAdmin() {
  const userId = document.getElementById('new-admin-id').value.trim();
  const username = document.getElementById('new-admin-name').value.trim();
  if (!userId) { showToast('유저 ID를 입력해주세요.', 'error'); return; }
  try {
    await Apex.post('/api/admins', { user_id: userId, username: username });
    showToast('관리자가 추가되었습니다.');
    document.getElementById('new-admin-id').value = '';
    document.getElementById('new-admin-name').value = '';
    loadAdmins();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function removeAdmin(userId) {
  if (!confirm('관리자 ' + userId + ' 을(를) 삭제할까요?')) return;
  try {
    await Apex.del('/api/admins/' + encodeURIComponent(userId));
    showToast('삭제되었습니다.');
    loadAdmins();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

/* ============================================================
   입금 웹훅 로그 / 테스트
   ============================================================ */
const LOG_COLORS = {
  deposit: '#5AA9FF',
  match: '#3DDC97',
  warn: '#FFA726',
  error: '#FF5C6C'
};

async function loadWebhookLogs() {
  const box = document.getElementById('webhook-logs-container');
  if (!box) return;
  box.innerHTML = '<span style="color:#8b96a8;">불러오는 중...</span>';
  try {
    const data = await Apex.get('/api/deposit-webhook/logs');
    const logs = (data && data.logs) || [];
    if (!logs.length) {
      box.innerHTML = '<span style="color:#8b96a8;">수신된 웹훅 로그가 없습니다.</span>';
      return;
    }
    box.innerHTML = logs.map((l) => {
      const color = LOG_COLORS[l.level] || '#94A0B4';
      return '<div style="margin-bottom:6px;">' +
        '<span style="color:#667287;">[' + esc(l.time) + ']</span> ' +
        '<span style="color:' + color + ';font-weight:700;">' + esc(l.level) + '</span> ' +
        '<span style="color:#E9EEF7;">' + esc(l.message) + '</span>' +
        '</div>';
    }).join('');
  } catch (err) {
    box.innerHTML = '<span style="color:#FF5C6C;">' + esc(err.message) + '</span>';
  }
}

async function clearWebhookLogs() {
  if (!confirm('입금 웹훅 로그를 모두 삭제할까요?')) return;
  try {
    await Apex.post('/api/deposit-webhook/logs/clear');
    showToast('로그가 삭제되었습니다.');
    loadWebhookLogs();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function testDepositWebhook() {
  const input = document.getElementById('webhook-test-text');
  const box = document.getElementById('webhook-test-result');
  const text = input ? input.value.trim() : '';
  if (!text) { showToast('토스 알림 문구를 입력해주세요.', 'error'); return; }

  if (box) box.innerHTML = '<span style="color:#8b96a8;">테스트 중...</span>';
  try {
    const data = await Apex.post('/api/deposit-webhook/test', { title: '토스', body: text });
    const parsed = data.parsed || {};
    const lines = [
      '<div style="line-height:1.9;">',
      '<b>금액</b> · ' + (parsed.amount ? fmt(parsed.amount) + '원' : '<span style="color:#FF5C6C;">추출 실패</span>'),
      '<br><b>입금자명</b> · ' + (parsed.depositor ? esc(parsed.depositor) : '<span style="color:#FF5C6C;">추출 실패</span>'),
      '<br><b>대기 요청</b> · ' + fmt(data.pending_count || 0) + '건',
      '<br><b>결과</b> · ' + esc(data.match_hint || '-'),
      '</div>'
    ];
    if (box) box.innerHTML = lines.join('');
    showToast('테스트 완료');
  } catch (err) {
    if (box) box.innerHTML = '<span style="color:#FF5C6C;">' + esc(err.message) + '</span>';
    showToast(err.message, 'error');
  }
}





