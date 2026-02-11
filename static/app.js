// 全局状态
let state = {};
let currentRoomId = null;
let ws = null;
let agentColors = {};
let colorIndex = 0;
let autoScroll = true;
let messagePollingTimer = null;

// AI名字颜色分配
function getAgentColor(name) {
    if (name === 'system') return 'sender-system';
    if (name === 'human') return 'sender-human';
    if (!agentColors[name]) {
        agentColors[name] = colorIndex++;
    }
    return `color-${agentColors[name] % 8}`;
}

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    connectWebSocket();
    fetchState();
    fetchRooms();
    // 定时刷新
    setInterval(fetchState, 3000);
    setInterval(fetchRooms, 5000);
});

// WebSocket连接
function connectWebSocket() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${location.host}/ws`);

    ws.onopen = () => console.log('WebSocket已连接');

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'state') {
            updateState(data.data);
        } else if (data.type === 'event') {
            addEventLog(data.data);
            // 如果当前聊天室有新消息就刷新
            if (currentRoomId) {
                fetchMessages(currentRoomId);
            }
        } else if (data.type === 'new_message') {
            if (data.message.chat_id === currentRoomId) {
                appendMessage(data.message);
            }
        }
    };

    ws.onclose = () => {
        console.log('WebSocket断开，3秒后重连...');
        setTimeout(connectWebSocket, 3000);
    };

    ws.onerror = (err) => console.error('WebSocket错误:', err);
}

// 获取状态
async function fetchState() {
    try {
        const resp = await fetch('/api/state');
        const data = await resp.json();
        updateState(data);
    } catch (e) {
        console.error('获取状态失败:', e);
    }
}

// 更新状态显示
function updateState(data) {
    state = data;

    // 顶部状态
    document.getElementById('day-display').textContent = `第${data.day + 1}天`;
    document.getElementById('tick-display').textContent = `第${data.tick}小时`;

    const aliveCount = Object.values(data.agents).filter(a => a.alive).length;
    const totalCount = Object.values(data.agents).length;
    document.getElementById('alive-display').textContent = `存活: ${aliveCount}/${totalCount}`;

    // AI列表
    renderAgentList(data.agents);

    // 事件日志
    if (data.recent_events) {
        renderEventLog(data.recent_events);
    }
}

// 渲染AI列表
function renderAgentList(agents) {
    const container = document.getElementById('agent-list');
    let html = '';

    // 日期进度条
    if (state.total_days) {
        html += '<div class="day-progress">';
        for (let i = 0; i < state.total_days; i++) {
            let cls = 'day-dot';
            if (i < state.day) cls += ' passed';
            else if (i === state.day) cls += ' current';
            html += `<div class="${cls}">${i + 1}</div>`;
        }
        html += '</div><br>';
    }

    for (const [name, agent] of Object.entries(agents)) {
        const colorClass = getAgentColor(name);
        const deadClass = agent.alive ? '' : ' dead';
        const dotClass = agent.alive ? 'alive' : 'dead';

        // 资源条宽度(最多显示5个)
        const cansPct = Math.min(100, (agent.cans / 5) * 100);
        const waterPct = Math.min(100, (agent.water / 5) * 100);

        html += `
        <div class="agent-card${deadClass}" onclick="showAgentDetail('${name}')">
            <div class="agent-name">
                <span class="alive-dot ${dotClass}"></span>
                <span class="${colorClass}">${name}</span>
                ${!agent.alive ? ' 💀' : ''}
            </div>
            <div class="agent-resources">
                <span>🥫 ${agent.cans}</span>
                <span>💧 ${agent.water}</span>
                <span>📅 ${agent.days_survived}天</span>
            </div>
            <div class="resource-bar-container">
                <div class="resource-bar">
                    <div class="resource-bar-fill cans" style="width:${cansPct}%"></div>
                </div>
                <div class="resource-bar" style="margin-top:2px">
                    <div class="resource-bar-fill water" style="width:${waterPct}%"></div>
                </div>
            </div>
            <div class="agent-traits">
                ${agent.traits.map(t => `<span class="trait-tag">${t}</span>`).join('')}
            </div>
        </div>`;
    }

    container.innerHTML = html;
}

// 渲染事件日志
function renderEventLog(events) {
    const container = document.getElementById('event-log');
    const wasAtBottom = container.scrollTop + container.clientHeight >= container.scrollHeight - 20;

    let html = '';
    // 只显示最近30条
    const recent = events.slice(-30);
    for (const evt of recent) {
        let cls = 'event-item';
        if (evt.type === 'death') cls += ' death';
        if (evt.type === 'trade_offer' || evt.type === 'trade_result') cls += ' trade';
        html += `<div class="${cls}">[D${evt.day + 1}T${evt.tick}] ${evt.content}</div>`;
    }
    container.innerHTML = html;

    if (wasAtBottom) {
        container.scrollTop = container.scrollHeight;
    }
}

// 添加单条事件
function addEventLog(event) {
    const container = document.getElementById('event-log');
    let cls = 'event-item';
    if (event.type === 'death') cls += ' death';
    if (event.type === 'trade_offer' || event.type === 'trade_result') cls += ' trade';
    const div = document.createElement('div');
    div.className = cls;
    div.textContent = `[D${event.day + 1}T${event.tick}] ${event.content}`;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
}

// 获取聊天室列表
async function fetchRooms() {
    try {
        const resp = await fetch('/api/rooms');
        const rooms = await resp.json();
        renderRooms(rooms);
    } catch (e) {
        console.error('获取聊天室失败:', e);
    }
}

// 渲染聊天室列表
function renderRooms(rooms) {
    const publicContainer = document.getElementById('public-rooms');
    const privateContainer = document.getElementById('private-rooms');
    let publicHtml = '';
    let privateHtml = '';

    for (const [rid, room] of Object.entries(rooms)) {
        const activeClass = rid === currentRoomId ? ' active' : '';
        const memberList = room.members.join(', ');
        const msgCount = room.message_count || 0;

        const item = `
        <div class="room-item${activeClass}" onclick="selectRoom('${rid}')">
            <span class="room-name">${room.human_aware ? '🔓' : '🔒'} ${room.name}</span>
            <span class="room-meta">${memberList} · ${msgCount}条消息</span>
        </div>`;

        if (room.human_aware) {
            publicHtml += item;
        } else {
            privateHtml += item;
        }
    }

    publicContainer.innerHTML = publicHtml || '<div style="color:#4b5563;font-size:12px;padding:8px;">暂无</div>';
    privateContainer.innerHTML = privateHtml || '<div style="color:#4b5563;font-size:12px;padding:8px;">暂无</div>';
}

// 选择聊天室
async function selectRoom(roomId) {
    currentRoomId = roomId;

    // 更新UI
    document.querySelectorAll('.room-item').forEach(el => el.classList.remove('active'));
    event.currentTarget?.classList.add('active');

    // 获取聊天室信息
    const rooms = state.rooms || {};
    const room = rooms[roomId];

    if (room) {
        document.getElementById('chat-room-name').textContent = room.name;
        document.getElementById('chat-room-info').textContent =
            `成员: ${room.members.join(', ')} | ${room.human_aware ? '公开' : '私密'}`;

        // 显示/隐藏输入框
        if (room.human_joined) {
            document.getElementById('chat-input-area').style.display = 'flex';
            document.getElementById('chat-readonly-notice').style.display = 'none';
        } else {
            document.getElementById('chat-input-area').style.display = 'none';
            document.getElementById('chat-readonly-notice').style.display = 'block';
        }
    }

    // 获取消息
    await fetchMessages(roomId);

    // 开始轮询消息
    if (messagePollingTimer) clearInterval(messagePollingTimer);
    messagePollingTimer = setInterval(() => fetchMessages(roomId), 3000);
}

// 获取消息
async function fetchMessages(roomId) {
    try {
        const resp = await fetch(`/api/rooms/${roomId}/messages?limit=200`);
        const messages = await resp.json();
        renderMessages(messages);
    } catch (e) {
        console.error('获取消息失败:', e);
    }
}

// 渲染消息列表
function renderMessages(messages) {
    const container = document.getElementById('chat-messages');
    const wasAtBottom = container.scrollTop + container.clientHeight >= container.scrollHeight - 50;

    let html = '';
    for (const msg of messages) {
        html += renderSingleMessage(msg);
    }
    container.innerHTML = html;

    // 自动滚动到底部
    if (wasAtBottom || autoScroll) {
        container.scrollTop = container.scrollHeight;
    }
}

// 渲染单条消息
function renderSingleMessage(msg) {
    let senderClass = 'sender-ai';
    let colorClass = getAgentColor(msg.sender);

    if (msg.sender === 'system') {
        senderClass = 'sender-system';
        colorClass = '';
    } else if (msg.sender === 'human') {
        senderClass = 'sender-human';
        colorClass = '';
    }

    const timeStr = `D${msg.day + 1} T${msg.tick}`;

    return `
    <div class="message ${senderClass}">
        <div class="msg-header">
            <span class="msg-sender ${colorClass}">
                ${msg.sender === 'system' ? '⚙️ 系统' : msg.sender === 'human' ? '👤 你' : '🤖 ' + msg.sender}
            </span>
            <span class="msg-time">${timeStr}</span>
        </div>
        <div class="msg-content">${escapeHtml(msg.content)}</div>
    </div>`;
}

// 追加单条消息
function appendMessage(msg) {
    const container = document.getElementById('chat-messages');
    const wasAtBottom = container.scrollTop + container.clientHeight >= container.scrollHeight - 50;

    container.insertAdjacentHTML('beforeend', renderSingleMessage(msg));

    if (wasAtBottom) {
        container.scrollTop = container.scrollHeight;
    }
}

// 发送消息
async function sendMessage() {
    const input = document.getElementById('chat-input');
    const content = input.value.trim();
    if (!content || !currentRoomId) return;

    input.value = '';

    try {
        const resp = await fetch(`/api/rooms/${currentRoomId}/send`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content })
        });
        const data = await resp.json();
        if (data.error) {
            alert(data.error);
        } else {
            appendMessage(data);
        }
    } catch (e) {
        console.error('发送失败:', e);
    }
}

// 显示AI详情
async function showAgentDetail(name) {
    const modal = document.getElementById('agent-modal');
    modal.style.display = 'flex';

    document.getElementById('modal-agent-name').textContent = `🤖 ${name}`;

    // 基本信息
    const agent = state.agents[name];
    let detailHtml = `
        <p><strong>状态:</strong> ${agent.alive ? '✅ 存活' : '💀 死亡'}</p>
        <p><strong>性格:</strong> ${agent.personality}</p>
        <p><strong>资源:</strong> 🥫 ${agent.cans}罐头 💧 ${agent.water}瓶水</p>
        <p><strong>存活天数:</strong> ${agent.days_survived}天</p>
        <p><strong>特征:</strong> ${agent.traits.join(', ')}</p>
    `;
    document.getElementById('modal-agent-details').innerHTML = detailHtml;

    // 获取记忆
    try {
        const resp = await fetch(`/api/agents/${name}/memory`);
        const data = await resp.json();

        // 记忆
        let memHtml = '';
        if (data.memory && data.memory.length > 0) {
            for (const mem of data.memory.slice(-30)) {
                memHtml += `<div class="memory-item">${escapeHtml(mem)}</div>`;
            }
        } else {
            memHtml = '<div style="color:#6b7280;font-size:12px;">暂无记忆</div>';
        }
        document.getElementById('modal-agent-memory').innerHTML = memHtml;

        // 关系
        let relHtml = '';
        if (data.relationships && Object.keys(data.relationships).length > 0) {
            for (const [other, rel] of Object.entries(data.relationships)) {
                const trust = rel.trust || 50;
                let trustClass = 'trust-mid';
                if (trust >= 70) trustClass = 'trust-high';
                else if (trust <= 30) trustClass = 'trust-low';

                relHtml += `
                <div class="relation-item">
                    <span class="relation-name">${other}</span>
                    <span class="relation-trust ${trustClass}">信任度: ${trust}</span>
                </div>`;

                if (rel.events) {
                    for (const evt of rel.events.slice(-3)) {
                        relHtml += `<div class="memory-item" style="margin-left:16px;font-size:11px;">${escapeHtml(evt)}</div>`;
                    }
                }
            }
        } else {
            relHtml = '<div style="color:#6b7280;font-size:12px;">暂无关系记录</div>';
        }
        document.getElementById('modal-agent-relations').innerHTML = relHtml;

    } catch (e) {
        console.error('获取记忆失败:', e);
    }
}

// 关闭弹窗
function closeModal() {
    document.getElementById('agent-modal').style.display = 'none';
}

// 点击弹窗外部关闭
document.addEventListener('click', (e) => {
    const modal = document.getElementById('agent-modal');
    if (e.target === modal) {
        modal.style.display = 'none';
    }
});

// 控制模拟
async function control(action) {
    try {
        const resp = await fetch(`/api/control/${action}`, { method: 'POST' });
        const data = await resp.json();
        if (data.tick_interval !== undefined) {
            document.getElementById('speed-display').textContent = `间隔: ${data.tick_interval}s`;
        }
    } catch (e) {
        console.error('控制失败:', e);
    }
}

// HTML转义
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}