#!/usr/bin/env python3
import http.server
import socketserver
import json
import sqlite3
import os
import urllib.parse
from datetime import datetime

PORT = 8080
DB_FILE = "voltbench.db"

# --- 1. АВТОМАТИЧЕСКАЯ ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ SQLITE ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    # Таблица всех прогонов (полная история со всеми метриками ИИ)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user TEXT NOT NULL,
            device TEXT NOT NULL,
            soc TEXT NOT NULL,
            cores INTEGER DEFAULT 8,
            emu_score INTEGER NOT NULL,
            game_score INTEGER NOT NULL,
            ai_score INTEGER NOT NULL,
            total_score INTEGER NOT NULL,
            ai_tier TEXT NOT NULL,
            ai_tokens_1b REAL,
            ai_tokens_3b REAL,
            ai_tokens_7b REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- 2. МАРШРУТИЗАЦИЯ И API ---
class VoltBenchHandler(http.server.SimpleHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # API: Получение топа участников (по последнему тесту)
        if path == "/api/leaderboard":
            soc_filter = query.get('soc', ['ALL'])[0]
            conn = sqlite3.connect(DB_FILE)
            cur = conn.cursor()

            # Выбираем строго ПОСЛЕДНИЙ прогон для каждого пользователя
            sql = '''
                SELECT r.id, r.user, r.device, r.soc, r.total_score, r.ai_score, r.ai_tier,
                       r.ai_tokens_1b, r.ai_tokens_3b, r.ai_tokens_7b,
                       datetime(r.created_at, 'localtime') as ts,
                       (SELECT COUNT(*) FROM runs sub WHERE LOWER(sub.user) = LOWER(r.user)) as run_count
                FROM runs r
                WHERE r.id IN (
                    SELECT MAX(id) FROM runs GROUP BY LOWER(user)
                )
            '''
            params = []
            if soc_filter != "ALL":
                sql += " AND LOWER(r.soc) LIKE ?"
                params.append(f"%{soc_filter.lower()}%")

            sql += " ORDER BY r.total_score DESC"
            cur.execute(sql, params)
            rows = cur.fetchall()
            conn.close()

            results = []
            for row in rows:
                results.append({
                    "id": row[0],
                    "user": row[1],
                    "device": row[2],
                    "soc": row[3],
                    "total": row[4],
                    "ai_score": row[5],
                    "ai_tier": row[6],
                    "tokens_1b": row[7],
                    "tokens_3b": row[8],
                    "tokens_7b": row[9],
                    "timestamp": row[10],
                    "runs_count": row[11]
                })

            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(results, ensure_ascii=False).encode('utf-8'))
            return

        # API: История всех запусков конкретного пользователя
        elif path == "/api/history":
            user = query.get('user', [''])[0]
            conn = sqlite3.connect(DB_FILE)
            cur = conn.cursor()
            cur.execute('''
                SELECT id, device, soc, emu_score, game_score, ai_score, total_score,
                       ai_tier, datetime(created_at, 'localtime')
                FROM runs
                WHERE LOWER(user) = LOWER(?)
                ORDER BY id DESC
            ''', (user,))
            rows = cur.fetchall()
            conn.close()

            history = []
            for r in rows:
                history.append({
                    "id": r[0], "device": r[1], "soc": r[2],
                    "emu": r[3], "game": r[4], "ai": r[5], "total": r[6],
                    "tier": r[7], "timestamp": r[8]
                })

            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(history, ensure_ascii=False).encode('utf-8'))
            return

        # Всё остальное раздаётся как статика (index.html и т.д.)
        super().do_GET()

    def do_POST(self):
        if self.path == "/api/submit":
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            try:
                data = json.loads(body)
            except Exception:
                self.send_error(400, "Invalid JSON")
                return

            # Вычисление прогнозируемых токенов для ИИ
            ai_score = int(data.get('ai', 0))
            tokens_1b = round(ai_score * 0.038 + 5.0, 1)
            tokens_3b = round(ai_score * 0.016 + 1.5, 1)
            tokens_7b = round(ai_score * 0.005 + 0.5, 1)

            conn = sqlite3.connect(DB_FILE)
            cur = conn.cursor()
            cur.execute('''
                INSERT INTO runs (user, device, soc, cores, emu_score, game_score, ai_score, total_score, ai_tier, ai_tokens_1b, ai_tokens_3b, ai_tokens_7b)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                data.get('user', 'Anonymous'),
                data.get('device', 'Unknown Device'),
                data.get('soc', 'Unknown SoC'),
                int(data.get('cores', 8)),
                int(data.get('emu', 0)),
                int(data.get('game', 0)),
                ai_score,
                int(data.get('total', 0)),
                data.get('tier', 'TIER B'),
                tokens_1b,
                tokens_3b,
                tokens_7b
            ))
            run_id = cur.lastrowid
            conn.commit()
            conn.close()

            print(f"[+] Новый результат #{run_id} от {data.get('user')} | {data.get('soc')} -> {data.get('total')} pts")

            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "run_id": run_id}).encode('utf-8'))
            return

        self.send_error(404, "Endpoint not found")

# Запуск сервера
if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), VoltBenchHandler) as httpd:
        print("=" * 50)
        print(f"⚡ СЕРВЕР VOLTBENCH ЗАПУЩЕН НА ПОРТУ {PORT}")
        print(f"👉 Откройте в браузере: http://localhost:{PORT}")
        print(f"📁 База данных SQLite : {DB_FILE} (создаётся сама)")
        print("=" * 50)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[!] Сервер остановлен.")
