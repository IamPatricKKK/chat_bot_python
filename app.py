from flask import Flask, render_template, request, jsonify
from openai import OpenAI
import os, json, uuid
import threading
from threading import Lock
from datetime import datetime

app = Flask(__name__)

client = OpenAI(
    base_url='http://localhost:11434/v1',
    api_key='ollama',
)

CHAT_FILE = 'chat_data/chathistory.json'
ASSISTANT_PROMPT = """
Tôi là một trợ lý AI thông minh.
Bạn cần giúp gì nào
...
"""

lock = Lock()  # để tránh race condition đọc ghi file



def load_chats():
    if not os.path.exists(CHAT_FILE):
        return []
    with open(CHAT_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_chats(chats):
    with open(CHAT_FILE, 'w', encoding='utf-8') as f:
        json.dump(chats, f, ensure_ascii=False, indent=2)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/chat_list')
def chat_list():
    """Trả về danh sách cuộc chat (id, title)"""
    chats = load_chats()
    sorted_chats = sorted(chats, key=lambda c: c.get("updatedAt", ""), reverse=True)
    return jsonify([{"id": c["id"], "title": c["title"], "updatedAt": c.get("updatedAt")} for c in sorted_chats])

@app.route('/chat/<chat_id>', methods=['GET'])
def get_chat(chat_id):
    """Lấy messages của cuộc chat theo id"""
    chats = load_chats()
    for c in chats:
        if c["id"] == chat_id:
            return jsonify(c)
    return jsonify({"error": "Chat not found"}), 404

def now_iso():
    return datetime.utcnow().isoformat() + "Z"

@app.route('/chat', methods=['POST'])
def new_chat():
    """Tạo cuộc chat mới"""
    data = request.json
    title = data.get("title", "Cuộc trò chuyện mới")
    new_chat = {
        "id": str(uuid.uuid4()),
        "title": title,
        "messages": [{"role": "system", "content": ASSISTANT_PROMPT}],
        "updatedAt": now_iso()
    }
    with lock:
        chats = load_chats()
        chats.append(new_chat)
        save_chats(chats)
    return jsonify(new_chat)

@app.route('/chat/<chat_id>/rename', methods=['POST'])
def rename_chat(chat_id):
    data = request.json
    new_title = data.get("title", "").strip()
    if not new_title:
        return jsonify({"error": "Title empty"}), 400
    with lock:
        chats = load_chats()
        for c in chats:
            if c["id"] == chat_id:
                c["title"] = new_title
                save_chats(chats)
                return jsonify({"success": True})
    return jsonify({"error": "Chat not found"}), 404

@app.route('/chat/<chat_id>', methods=['DELETE'])
def delete_chat(chat_id):
    with lock:
        chats = load_chats()
        new_chats = [c for c in chats if c["id"] != chat_id]
        if len(new_chats) == len(chats):
            return jsonify({"error": "Chat not found"}), 404
        save_chats(new_chats)
    return jsonify({"success": True})



#===== Thiết kế Chat bot ======

messages = [{"role": "system", "content": ASSISTANT_PROMPT}]
tasks = []

@app.route('/chat/<chat_id>/message', methods=['POST'])
def chat_message(chat_id):
    user_msg = request.json.get("message", "").strip()
    if not user_msg:
        return jsonify({"error": "Empty message"}), 400

    with lock:
        chats = load_chats()
        chat = next((c for c in chats if c["id"] == chat_id), None)
        if not chat:
            return jsonify({"error": "Chat not found"}), 404

        chat["messages"].append({"role": "user", "content": user_msg})

        # Gửi request chat đến OpenAI client
        response = client.chat.completions.create(
            model="gemma3",
            stream=False,
            messages=chat["messages"]
        )
        
        bot_reply = response.choices[0].message.content
        chat["messages"].append({"role": "assistant", "content": bot_reply})

        chat["updatedAt"] = now_iso()

        save_chats(chats)

    return jsonify({"reply": bot_reply})


if __name__ == '__main__':
    if not os.path.exists('chat_data'):
        os.mkdir('chat_data')
    app.run(debug=True)
