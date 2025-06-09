// Lấy các phần tử HTML cần sử dụng từ DOM
const chatListEl = document.getElementById("chat-list");     // Danh sách các cuộc trò chuyện
const chatBox = document.getElementById("chat-box");          // Hộp hiển thị nội dung trò chuyện
const inputMsg = document.getElementById("input-msg");        // Ô nhập tin nhắn
const sendBtn = document.getElementById("send-btn");          // Nút gửi tin nhắn
const newChatBtn = document.getElementById("new-chat-btn");   // Nút tạo cuộc trò chuyện mới

// Khai báo biến lưu trữ ID cuộc trò chuyện hiện tại và danh sách các cuộc trò chuyện
let currentChatId = null;
let chats = [];

/**
 * Thêm một tin nhắn vào khung chat
 * @param {string} text - Nội dung tin nhắn
 * @param {string} sender - "user" hoặc "bot" để xác định người gửi
 */
function appendMessage(text, sender) {
    if (sender === "system") {
        // Không hiển thị tin nhắn system
        return; 
    }

    const div = document.createElement("div");
    div.className = sender === "user" ? "user-msg" : "bot-msg";

    // Nếu là bot thì hiển thị bằng markdown
    if (sender === "bot") {
    div.innerHTML = marked.parse(text); // Parse Markdown
    }
    else {
    div.textContent = text;
    }

    chatBox.appendChild(div);
    chatBox.scrollTop = chatBox.scrollHeight; // Tự động cuộn xuống dưới cùng
}

/**
 * Hiển thị danh sách các cuộc trò chuyện bên trái
 */
function renderChatList() {
  chatListEl.innerHTML = ''; // Xóa danh sách cũ

  chats.forEach(c => {
    const div = document.createElement("div");
    div.className = "chat-item" + (c.id === currentChatId ? " active" : ""); // Thêm class active nếu là cuộc trò chuyện hiện tại
    div.dataset.id = c.id;

    const titleSpan = document.createElement("span");
    titleSpan.className = "chat-title";
    titleSpan.textContent = c.title;

    // Nhóm nút đổi tên và xóa
    const btnGroup = document.createElement("span");
    btnGroup.className = "btn-group";
    btnGroup.style.display = "flex";
    btnGroup.style.gap = "10px";
    btnGroup.style.alignItems = "center";

    // Nút đổi tên
    const renameBtn = document.createElement("span");
    renameBtn.className = "rename-btn";
    renameBtn.textContent = "✏️";
    renameBtn.title = "Đổi tên";
    renameBtn.style.cursor = "pointer";

    // Sự kiện đổi tên
    renameBtn.addEventListener("click", (e) => {
      e.stopPropagation(); // Không kích hoạt sự kiện chọn chat
      const newTitle = prompt("Nhập tên mới cho cuộc trò chuyện:", c.title);
      if (newTitle && newTitle.trim()) {
        fetch(`/chat/${c.id}/rename`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title: newTitle.trim() })
        })
        .then(res => res.json())
        .then(data => {
          if (!data.error) {
            c.title = newTitle.trim();
            renderChatList(); // Cập nhật lại danh sách
          } else {
            alert("Lỗi đổi tên: " + data.error);
          }
        });
      }
    });

    // Nút xóa
    const deleteBtn = document.createElement("span");
    deleteBtn.className = "delete-btn";
    deleteBtn.textContent = "🗑️";
    deleteBtn.title = "Xóa cuộc trò chuyện";
    deleteBtn.style.cursor = "pointer";

    // Sự kiện xóa
    deleteBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (confirm(`Bạn có chắc muốn xóa cuộc trò chuyện "${c.title}"?`)) {
        fetch(`/chat/${c.id}`, { method: "DELETE" })
        .then(res => res.json())
        .then(data => {
          if (!data.error) {
            chats = chats.filter(chat => chat.id !== c.id);
            // Nếu đang xem chat bị xóa thì chuyển về chat khác
            if (currentChatId === c.id) {
              currentChatId = chats.length ? chats[0].id : null;
              if (currentChatId) loadChat(currentChatId);
              else chatBox.innerHTML = '';
            }
            renderChatList();
          } else {
            alert("Lỗi xóa cuộc trò chuyện: " + data.error);
          }
        });
      }
    });

    // Gộp nút vào nhóm
    btnGroup.appendChild(renameBtn);
    btnGroup.appendChild(deleteBtn);

    // Gộp phần tiêu đề và nhóm nút vào phần tử chính
    div.appendChild(titleSpan);
    div.appendChild(btnGroup);

    // Sự kiện chọn cuộc trò chuyện
    div.addEventListener("click", () => {
      if (c.id !== currentChatId) {
        currentChatId = c.id;
        loadChat(c.id);
        renderChatList(); // Đánh dấu lại chat đang active
      }
    });

    chatListEl.appendChild(div);
  });
}

/**
 * Tải danh sách các cuộc trò chuyện từ server
 */
async function loadChatList() {
  const res = await fetch('/chat_list');
  chats = await res.json();
  if (!currentChatId && chats.length > 0) currentChatId = chats[0].id; // Chọn chat đầu tiên nếu chưa có
  renderChatList();
  if (currentChatId) loadChat(currentChatId);
}

/**
 * Tải toàn bộ tin nhắn của một cuộc trò chuyện
 * @param {string} chatId - ID cuộc trò chuyện
 */
async function loadChat(chatId) {
  chatBox.innerHTML = '';     // Xóa nội dung chat cũ
  inputMsg.value = '';        // Xóa nội dung ô nhập
  sendBtn.disabled = false;   // Cho phép gửi lại

  const res = await fetch(`/chat/${chatId}`);
  if (res.status !== 200) {
    alert("Không tìm thấy cuộc trò chuyện");
    return;
  }

  const chatData = await res.json();
  chatData.messages.forEach(msg => {
    appendMessage(msg.content, msg.role === "user" ? "user" : "bot");
  });
  inputMsg.focus();
}

/**
 * Gửi tin nhắn người dùng và nhận phản hồi từ bot
 */
async function sendMessage() {
  const message = inputMsg.value.trim();
  if (!message || !currentChatId) return;

  appendMessage(message, "user"); // Hiển thị tin nhắn của user
  inputMsg.value = "";
  sendBtn.disabled = true;

  // Hiển thị "Đang phản hồi..." tạm thời
  const loaderDiv = document.createElement("div");
  loaderDiv.className = "bot-msg";
  loaderDiv.textContent = "Đang phản hồi...";
  loaderDiv.id = "loading-indicator";
  chatBox.appendChild(loaderDiv);
  chatBox.scrollTop = chatBox.scrollHeight;

  try {
    const response = await fetch(`/chat/${currentChatId}/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message })
    });

    const data = await response.json();
    if (data.error) {
      alert("Lỗi: " + data.error);
    } else {
      loaderDiv.remove(); // Xóa "Đang phản hồi..."
      appendMessage(data.reply, "bot"); // Hiển thị phản hồi từ bot
    }
  } catch (err) {
    loaderDiv.remove();
    alert("Đã xảy ra lỗi mạng.");
  }

  // Nếu tiêu đề là "new chat", đổi tên bằng nội dung tin nhắn đầu
  if (chats.find(c => c.id === currentChatId)?.title === "new chat") {
    const suggestedTitle = message.length > 30 ? message.slice(0, 30) + "..." : message;
    fetch(`/chat/${currentChatId}/rename`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: suggestedTitle })
    }).then(res => res.json())
    .then(data => {
      if (!data.error) {
        const chat = chats.find(c => c.id === currentChatId);
        if (chat) chat.title = suggestedTitle;
        renderChatList();
      }
    });
  }

  sendBtn.disabled = false;
  inputMsg.focus();
}

/**
 * Xử lý khi người dùng bấm nút "New Chat"
 */
newChatBtn.addEventListener("click", async () => {
  const title = "new chat";
  const res = await fetch('/chat', {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: title })
  });
  const newChat = await res.json();
  chats.unshift(newChat); // Thêm vào đầu danh sách
  currentChatId = newChat.id;
  renderChatList();
  loadChat(currentChatId);
});

// Cho phép Shift+Enter để xuống dòng, Enter để gửi
inputMsg.addEventListener("keydown", e => {
    if (!e.shiftKey && e.key === "Enter") {
        e.preventDefault(); // Ngăn xuống dòng
        sendMessage();
    }
});

// Tự động resize khung nhập khi gõ nhiều dòng (nếu muốn)
inputMsg.addEventListener("input", () => {
    inputMsg.style.height = "auto";
    inputMsg.style.height = inputMsg.scrollHeight + "px";
});

// Gửi tin nhắn khi nhấn Enter
// inputMsg.addEventListener("keydown", e => {
//     if (e.key === "Enter") sendMessage();
// });

// Gửi tin nhắn khi nhấn nút Gửi
sendBtn.addEventListener("click", sendMessage);

// Tự động tải danh sách chat khi trang web load
window.onload = loadChatList;
