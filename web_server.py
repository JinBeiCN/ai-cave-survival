import asyncio
import json
from aiohttp import web
import aiohttp_cors

class WebServer:
    """Web服务器 - 提供前端界面和API"""

    def __init__(self, simulation, host="0.0.0.0", port=8080):
        self.sim = simulation
        self.host = host
        self.port = port
        self.app = web.Application()
        self.ws_clients = []  # WebSocket客户端
        self._setup_routes()

        # 注册事件回调
        self.sim.on_event = self._broadcast_event

    def _setup_routes(self):
        """注册路由"""
        self.app.router.add_get('/', self._index)
        self.app.router.add_static('/static', 'static')
        self.app.router.add_get('/api/state', self._get_state)
        self.app.router.add_get('/api/rooms', self._get_rooms)
        self.app.router.add_get('/api/rooms/{room_id}/messages', self._get_messages)
        self.app.router.add_post('/api/rooms/{room_id}/send', self._send_message)
        self.app.router.add_post('/api/control/{action}', self._control)
        self.app.router.add_get('/api/agents/{name}', self._get_agent)
        self.app.router.add_get('/api/agents/{name}/memory', self._get_agent_memory)
        self.app.router.add_get('/ws', self._websocket)

        # CORS
        cors = aiohttp_cors.setup(self.app, defaults={
            "*": aiohttp_cors.ResourceOptions(
                allow_credentials=True, expose_headers="*",
                allow_headers="*", allow_methods="*"
            )
        })
        for route in list(self.app.router.routes()):
            try:
                cors.add(route)
            except:
                pass

    async def _index(self, request):
        """主页"""
        return web.FileResponse('templates/index.html')

    async def _get_state(self, request):
        """获取模拟状态"""
        return web.json_response(self.sim.get_state())

    async def _get_rooms(self, request):
        """获取所有聊天室(人类视角=全部)"""
        rooms = self.sim.chat.get_all_rooms_for_human()
        data = {}
        for rid, room in rooms.items():
            d = room.to_dict()
            d["can_speak"] = room.human_joined
            data[rid] = d
        return web.json_response(data)

    async def _get_messages(self, request):
        """获取聊天室消息"""
        room_id = request.match_info['room_id']
        limit = int(request.query.get('limit', 100))
        msgs = self.sim.chat.get_room_messages(room_id, limit)
        return web.json_response([m.to_dict() for m in msgs])

    async def _send_message(self, request):
        """人类发送消息"""
        room_id = request.match_info['room_id']
        data = await request.json()
        content = data.get("content", "")
        if not content:
            return web.json_response({"error": "空消息"}, status=400)

        msg = self.sim.human_send_message(room_id, content)
        if msg:
            await self._broadcast({"type": "new_message", "message": msg.to_dict()})
            return web.json_response(msg.to_dict())
        return web.json_response({"error": "无法在此聊天室发言"}, status=403)

    async def _control(self, request):
        """控制模拟"""
        action = request.match_info['action']
        if action == "pause":
            self.sim.paused = True
        elif action == "resume":
            self.sim.paused = False
        elif action == "speed_up":
            self.sim.tick_interval = max(1, self.sim.tick_interval - 2)
        elif action == "slow_down":
            self.sim.tick_interval = min(60, self.sim.tick_interval + 2)
        return web.json_response({"status": "ok", "paused": self.sim.paused,
                                   "tick_interval": self.sim.tick_interval})

    async def _get_agent(self, request):
        """获取AI详情"""
        name = request.match_info['name']
        if name in self.sim.agents:
            return web.json_response(self.sim.agents[name].get_status())
        return web.json_response({"error": "未找到"}, status=404)

    async def _get_agent_memory(self, request):
        """获取AI记忆(人类偷看)"""
        name = request.match_info['name']
        if name in self.sim.agents:
            return web.json_response({
                "name": name,
                "memory": self.sim.agents[name].memory,
                "relationships": self.sim.agents[name].relationships
            })
        return web.json_response({"error": "未找到"}, status=404)

    async def _websocket(self, request):
        """WebSocket连接"""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.ws_clients.append(ws)

        try:
            # 发送初始状态
            await ws.send_json({"type": "state", "data": self.sim.get_state()})
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    pass  # 可扩展
                elif msg.type == web.WSMsgType.ERROR:
                    break
        finally:
            self.ws_clients.remove(ws)
        return ws

    async def _broadcast(self, data):
        """广播消息给所有WebSocket客户端"""
        for ws in self.ws_clients[:]:
            try:
                await ws.send_json(data)
            except:
                self.ws_clients.remove(ws)

    def _broadcast_event(self, event):
        """事件回调 - 广播给前端"""
        asyncio.ensure_future(self._broadcast({
            "type": "event",
            "data": event
        }))
        # 同时广播状态更新
        asyncio.ensure_future(self._broadcast({
            "type": "state",
            "data": self.sim.get_state()
        }))

    async def start(self):
        """启动服务器"""
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        print(f"🌐 服务器启动: http://localhost:{self.port}")