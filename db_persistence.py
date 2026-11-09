"""DB 영속성 (Render 무료 플랜 디스크 초기화 대응)

Render 무료 플랜은 재배포/재시작 때 파일시스템이 초기화되어 data/vending.db 가 사라진다.
이 모듈은 디스코드 채널을 저장소로 사용해 DB 를 자동 백업/복원한다.

동작
- restore(): 부팅 시 로컬 DB 가 없으면, 백업 채널의 최신 첨부파일을 내려받아 복원
- backup_loop(): 주기적으로 DB 변경을 감지해 업로드하고 이전 백업 메시지는 삭제

필요 설정 (Render Environment)
- DISCORD_TOKEN              : 이미 사용 중인 봇 토큰 (파일 업로드 권한 필요)
- DB_BACKUP_CHANNEL_ID       : 백업용 채널 ID (없으면 관리자 채널 ID 사용)
"""

import os
import io
import time
import json
import sqlite3
import threading

import requests

API = 'https://discord.com/api/v10'
FILENAME = 'apex-vending-db.db'
BACKUP_INTERVAL = 30      # 초 (변경 감지 주기)
KEEP_MESSAGES = 1         # 채널에 남길 백업 메시지 수


def _token():
    return (os.environ.get('DISCORD_TOKEN') or '').strip()


def _channel_id():
    cid = (os.environ.get('DB_BACKUP_CHANNEL_ID') or '').strip()
    if cid:
        return cid
    # 환경변수가 없으면 기본 관리자 채널 ID 사용 (database.DEFAULT_SETTINGS 와 동일)
    try:
        import database as _db
        return str(_db.DEFAULT_SETTINGS.get('admin_channel_id', '') or '')
    except Exception:
        return ''


def enabled():
    flag = (os.environ.get('DB_BACKUP_ENABLED') or '1').strip().lower()
    if flag in ('0', 'false', 'no', 'off'):
        return False
    return bool(_token() and _channel_id())


def _headers():
    return {'Authorization': f'Bot {_token()}'}


def _find_backups(channel_id, limit=50):
    """채널에서 DB 백업 첨부가 있는 메시지 목록 (최신순)"""
    try:
        r = requests.get(f'{API}/channels/{channel_id}/messages',
                         headers=_headers(), params={'limit': limit}, timeout=6)
        if r.status_code != 200:
            return []
        found = []
        for m in r.json():
            for a in (m.get('attachments') or []):
                if str(a.get('filename', '')).startswith('apex-vending-db'):
                    found.append((m.get('id'), a.get('url'), a.get('filename')))
                    break
        return found
    except Exception as e:
        print(f'[DB-BACKUP] 목록 조회 실패: {e}')
        return []


def restore(db_path):
    """로컬 DB 가 없을 때 백업에서 복원. 복원 성공 시 True"""
    if not enabled():
        print('[DB-BACKUP] 복원 건너뜀 (DISCORD_TOKEN 또는 백업 채널 미설정)')
        return False
    if os.path.exists(db_path):
        return False
    channel = _channel_id()
    for msg_id, url, name in _find_backups(channel):
        try:
            r = requests.get(url, timeout=15)
            if r.status_code != 200 or len(r.content) < 1024:
                continue
            data = r.content
            # SQLite 파일 검증
            if b'SQLite format 3' not in data[:100]:
                print('[DB-BACKUP] 백업 파일이 SQLite 형식이 아님 - 건너뜀')
                continue
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            with open(db_path, 'wb') as f:
                f.write(data)
            print(f'[DB-BACKUP] 백업에서 DB 복원 완료 ({len(data)} bytes, msg {msg_id})')
            return True
        except Exception as e:
            print(f'[DB-BACKUP] 복원 실패: {e}')
    print('[DB-BACKUP] 복원할 백업이 없습니다 (첫 배포)')
    return False


def _snapshot_bytes(db_path):
    """실행 중인 SQLite 를 안전하게 복사 (sqlite backup API 사용)"""
    tmp_path = db_path + '.snap'
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(tmp_path)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    with open(tmp_path, 'rb') as f:
        data = f.read()
    try:
        os.remove(tmp_path)
    except Exception:
        pass
    return data


def backup_once(db_path):
    """DB 스냅샷을 채널에 업로드하고 오래된 백업 메시지 삭제"""
    if not enabled() or not os.path.exists(db_path):
        return False
    channel = _channel_id()
    try:
        data = _snapshot_bytes(db_path)
        files = {'files[0]': (FILENAME, data, 'application/octet-stream')}
        payload = {'content': f'DB 백업 {time.strftime("%Y-%m-%d %H:%M:%S")}'}
        r = requests.post(f'{API}/channels/{channel}/messages',
                          headers=_headers(),
                          data={'payload_json': json.dumps(payload)},
                          files=files, timeout=60)
        if r.status_code not in (200, 201):
            print(f'[DB-BACKUP] 업로드 실패 {r.status_code}: {r.text[:200]}')
            return False
        # 오래된 백업 정리
        for i, (msg_id, _url, _name) in enumerate(_find_backups(channel)):
            if i < KEEP_MESSAGES:
                continue
            try:
                requests.delete(f'{API}/channels/{channel}/messages/{msg_id}',
                                headers=_headers(), timeout=20)
            except Exception:
                pass
        return True
    except Exception as e:
        print(f'[DB-BACKUP] 백업 실패: {e}')
        return False


def start_backup_loop(db_path):
    """변경 감지 시 백업하는 백그라운드 스레드 시작"""
    if not enabled():
        return None

    def _loop():
        last = (None, 0)
        while True:
            try:
                st = os.stat(db_path) if os.path.exists(db_path) else None
                sig = (st.st_mtime, st.st_size) if st else (None, 0)
                if st and sig != last:
                    if backup_once(db_path):
                        last = sig
                        print('[DB-BACKUP] 자동 백업 완료')
            except Exception as e:
                print(f'[DB-BACKUP] 루프 오류: {e}')
            time.sleep(BACKUP_INTERVAL)

    t = threading.Thread(target=_loop, daemon=True, name='db-backup')
    t.start()
    return t
