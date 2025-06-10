# Nhập các thư viện cần thiết
from flask import Flask, render_template, request, jsonify  # Flask để tạo web server
from openai import OpenAI  # Sử dụng OpenAI API để gọi mô hình AI (ví dụ: ollama)
import os, json, uuid  # Quản lý file, dữ liệu JSON, và tạo ID duy nhất
import threading  # Dùng để xử lý đa luồng
from threading import Lock  # Lock để tránh xung đột khi truy cập file cùng lúc
from datetime import datetime  # Lấy thời gian hiện tại
import sqlite3  # Thêm thư viện SQLite
from contextlib import contextmanager  # Để tạo context manager cho database

# Khởi tạo ứng dụng Flask
app = Flask(__name__)

# Khởi tạo client kết nối tới API của mô hình AI (ở đây là Ollama chạy local)
client = OpenAI(
    base_url='http://localhost:11434/v1',
    api_key='ollama',
)

# Cấu hình database
DATABASE = 'chat_data/chatbot.db'

# Context manager để quản lý kết nối database
@contextmanager
def get_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    try:
        yield db
    finally:
        db.close()

# Khởi tạo database
def init_db():
    with get_db() as db:
        db.execute('''
        CREATE TABLE IF NOT EXISTS chats (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        ''')
        
        db.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE
        )
        ''')
        db.commit()

# Prompt hệ thống - khởi tạo để trợ lý AI hiểu vai trò của mình
ASSISTANT_PROMPT = """
Tôi là một trợ lý AI thông minh.
Bạn cần giúp gì nào
...
"""

# Đường dẫn file lưu lịch sử chat
CHAT_FILE = 'chat_data/chathistory.json'

# Khởi tạo Lock để tránh race condition khi ghi/đọc file chat
lock = Lock()

# Load danh sách các cuộc chat từ database
def load_chats():
    with get_db() as db:
        chats = db.execute('''
            SELECT id, title, updated_at
            FROM chats
            ORDER BY updated_at DESC
        ''').fetchall()
        return [dict(chat) for chat in chats]

# Load tin nhắn của một cuộc chat
def load_chat_messages(chat_id):
    with get_db() as db:
        messages = db.execute('''
            SELECT role, content
            FROM messages
            WHERE chat_id = ?
            ORDER BY created_at ASC
        ''', (chat_id,)).fetchall()
        return [dict(msg) for msg in messages]

# Route mặc định - trả về trang index.html
@app.route('/')
def home():
    return render_template('index.html')

# API trả về danh sách các cuộc trò chuyện
@app.route('/chat_list')
def chat_list():
    chats = load_chats()
    return jsonify(chats)

# API lấy chi tiết một cuộc trò chuyện theo id
@app.route('/chat/<chat_id>', methods=['GET'])
def get_chat(chat_id):
    with get_db() as db:
        chat = db.execute('''
            SELECT id, title, updated_at
            FROM chats
            WHERE id = ?
        ''', (chat_id,)).fetchone()
        
        if not chat:
            return jsonify({"error": "Chat not found"}), 404
            
        chat_dict = dict(chat)
        chat_dict['messages'] = load_chat_messages(chat_id)
        return jsonify(chat_dict)

# Hàm trả về thời gian hiện tại theo định dạng ISO
def now_iso():
    return datetime.utcnow().isoformat() + "Z"

# API tạo một cuộc trò chuyện mới
@app.route('/chat', methods=['POST'])
def new_chat():
    data = request.json
    title = data.get("title", "Cuộc trò chuyện mới")
    chat_id = str(uuid.uuid4())
    current_time = now_iso()
    
    with get_db() as db:
        # Tạo chat mới
        db.execute('''
            INSERT INTO chats (id, title, updated_at)
            VALUES (?, ?, ?)
        ''', (chat_id, title, current_time))
        
        # Thêm system message
        db.execute('''
            INSERT INTO messages (chat_id, role, content, created_at)
            VALUES (?, ?, ?, ?)
        ''', (chat_id, "system", ASSISTANT_PROMPT, current_time))
        
        db.commit()
        
    return jsonify({
        "id": chat_id,
        "title": title,
        "updatedAt": current_time,
        "messages": [{"role": "system", "content": ASSISTANT_PROMPT}]
    })

# Tạo tiêu đề từ tin nhắn đầu tiên của người dùng
def generate_title_from_messages(messages):
    first_user_msg = next((m["content"] for m in messages if m["role"] == "user"), "Chưa có chủ đề")
    return first_user_msg[:30] + "..." if len(first_user_msg) > 30 else first_user_msg

# API đổi tên cuộc trò chuyện
@app.route('/chat/<chat_id>/rename', methods=['POST'])
def rename_chat(chat_id):
    data = request.json
    new_title = data.get("title", "").strip()
    if not new_title:
        return jsonify({"error": "Title empty"}), 400
        
    with get_db() as db:
        db.execute('''
            UPDATE chats
            SET title = ?, updated_at = ?
            WHERE id = ?
        ''', (new_title, now_iso(), chat_id))
        db.commit()
        
        if db.total_changes == 0:
            return jsonify({"error": "Chat not found"}), 404
            
    return jsonify({"success": True})

# API xóa cuộc trò chuyện theo id
@app.route('/chat/<chat_id>', methods=['DELETE'])
def delete_chat(chat_id):
    with get_db() as db:
        db.execute('DELETE FROM chats WHERE id = ?', (chat_id,))
        db.commit()
        
        if db.total_changes == 0:
            return jsonify({"error": "Chat not found"}), 404
            
    return jsonify({"success": True})

# ===== Thiết kế Chat bot =====

messages = [{"role": "system", "content": ASSISTANT_PROMPT}]  # Danh sách tin nhắn mặc định ban đầu
tasks = []  # Placeholder cho xử lý nền nếu cần sau này

# API gửi tin nhắn và nhận phản hồi từ AI
@app.route('/chat/<chat_id>/message', methods=['POST'])
def chat_message(chat_id):
    user_msg = request.json.get("message", "").strip()
    if not user_msg:
        return jsonify({"error": "Empty message"}), 400

    current_time = now_iso()
    
    with get_db() as db:
        # Kiểm tra chat tồn tại
        chat = db.execute('SELECT title FROM chats WHERE id = ?', (chat_id,)).fetchone()
        if not chat:
            return jsonify({"error": "Chat not found"}), 404
            
        # Load tin nhắn cũ
        messages = load_chat_messages(chat_id)
        
        # Thêm tin nhắn người dùng
        db.execute('''
            INSERT INTO messages (chat_id, role, content, created_at)
            VALUES (?, ?, ?, ?)
        ''', (chat_id, "user", user_msg, current_time))
        
        # Cập nhật messages để gửi cho AI
        messages.append({"role": "user", "content": user_msg})
        
        # Gửi yêu cầu tới mô hình AI
        response = client.chat.completions.create(
            model="gemma3",
            stream=False,
            messages=messages
        )
        
        # Nhận phản hồi từ bot
        bot_reply = response.choices[0].message.content
        
        # Lưu tin nhắn của bot
        db.execute('''
            INSERT INTO messages (chat_id, role, content, created_at)
            VALUES (?, ?, ?, ?)
        ''', (chat_id, "assistant", bot_reply, current_time))
        
        # Cập nhật thời gian chat
        db.execute('''
            UPDATE chats
            SET updated_at = ?
            WHERE id = ?
        ''', (current_time, chat_id))
        
        # Nếu là tin nhắn đầu tiên, cập nhật tiêu đề
        title_changed = False
        if len(messages) == 1:  # Chỉ có system message
            try:
                title = user_msg[:30] + "..." if len(user_msg) > 30 else user_msg
                db.execute('''
                    UPDATE chats
                    SET title = ?
                    WHERE id = ?
                ''', (title, chat_id))
                title_changed = True
            except Exception as e:
                print("Tự đặt tiêu đề lỗi:", e)
                
        db.commit()
        
    return jsonify({"reply": bot_reply, "titleChanged": title_changed})

# Chạy ứng dụng Flask
if __name__ == '__main__':
    # Tạo thư mục nếu chưa có
    if not os.path.exists('chat_data'):
        os.mkdir('chat_data')
    # Khởi tạo database
    init_db()
    port = int(os.environ.get("PORT", 10000))  # Render sẽ cung cấp PORT qua biến môi trường
    app.run(host="0.0.0.0", port=port, debug=True)
