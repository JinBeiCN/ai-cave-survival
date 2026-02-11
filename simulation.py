import asyncio
import random
import time
import yaml
from ai_agent import AIAgent
from chat_system import ChatSystem
from resource_manager import ResourceManager
from llm_client import LLMClient

class Simulation:
    """模拟引擎 - 控制整个模拟流程"""

    def __init__(self, config_path="config.yaml"):
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)

        self.llm = LLMClient(self.config["llm"])
        self.chat = ChatSystem()

        sim_cfg = self.config["simulation"]
        self.total_days = sim_cfg["total_days"]
        self.tick_interval = sim_cfg["tick_interval"]
        self.ticks_per_day = sim_cfg["ticks_per_day"]

        # 创建AI代理
        self.agents: dict[str, AIAgent] = {}
        for agent_cfg in self.config["agents"]:
            agent = AIAgent(
                name=agent_cfg["name"],
                personality=agent_cfg["personality"],
                traits=agent_cfg["traits"],
                llm_client=self.llm
            )
            self.agents[agent.name] = agent
            self.chat.add_agent_to_defaults(agent.name)

        # 资源管理
        self.resource_mgr = ResourceManager(
            num_agents=len(self.agents),
            total_days=self.total_days,
            min_survivors=sim_cfg["min_survivors"]
        )

        # 时间状态
        self.current_day = 0
        self.current_tick = 0
        self.running = False
        self.paused = False

        # 事件回调
        self.on_event = None       # 事件回调函数
        self.event_log = []        # 事件日志
        self.pending_trades = {}   # 待处理交易

    async def start(self):
        """启动模拟"""
        self.running = True
        self._log_event("simulation_start", "模拟开始！AI们醒来发现自己在山洞中...")

        # 发送初始系统消息
        note = ("你们初始的食物在你们手边，分别是一个罐头和一瓶水。"
                "你们每天需要吃一个罐头喝一瓶水来维持基本生存。"
                "你们需要在这里坚持14天来等待救护的到来。")
        self.chat.send_message("ai_private", "system", f"📋 字条内容: {note}", 0, 0)
        self.chat.send_message("ai_public", "system", f"📋 字条内容: {note}", 0, 0)

        # 主循环
        while self.running and self.current_day < self.total_days:
            if self.paused:
                await asyncio.sleep(0.5)
                continue

            await self._process_tick()
            await asyncio.sleep(self.tick_interval)

        # 模拟结束
        self._end_simulation()

    async def _process_tick(self):
        """处理一个tick"""
        day = self.current_day
        tick = self.current_tick

        # 新的一天开始
        if tick == 0:
            await self._start_new_day(day)

        # AI思考和行动
        alive_agents = [a for a in self.agents.values() if a.alive]
        random.shuffle(alive_agents)

        for agent in alive_agents:
            try:
                decisions = await agent.think_and_decide(self.chat, day, tick)
                for decision_type, data in decisions:
                    await self._handle_decision(agent, decision_type, data, day, tick)
            except Exception as e:
                print(f"AI {agent.name} 思考出错: {e}")

        # 一天结束
        self.current_tick += 1
        if self.current_tick >= self.ticks_per_day:
            await self._end_day(day)
            self.current_tick = 0
            self.current_day += 1

    async def _start_new_day(self, day):
        """新一天开始 - 分配资源"""
        alive_names = [a.name for a in self.agents.values() if a.alive]
        distribution = self.resource_mgr.distribute(day, alive_names)

        total_cans = sum(d["cans"] for d in distribution.values())
        total_water = sum(d["water"] for d in distribution.values())

        # 系统通知
        sys_msg = f"📦 第{day+1}天开始！今日总资源: {total_cans}罐头, {total_water}瓶水"
        self.chat.send_message("ai_private", "system", sys_msg, day, 0)
        self.chat.send_message("ai_public", "system", sys_msg, day, 0)

        # 私信通知每个AI
        for name, res in distribution.items():
            agent = self.agents[name]
            agent.receive_resources(res["cans"], res["water"], day)
            personal_msg = f"🎒 {name}收到: {res['cans']}罐头, {res['water']}瓶水 (当前总计: {agent.cans}罐头, {agent.water}瓶水)"
            self.chat.send_message("ai_private", "system", personal_msg, day, 0)
            self._log_event("resource_distribution", personal_msg)

    async def _end_day(self, day):
        """一天结束 - 强制消耗资源"""
        for agent in self.agents.values():
            if not agent.alive:
                continue
            if not agent.consume_daily():
                death_msg = f"💀 {agent.name}因资源不足死亡了！"
                self.chat.send_message("ai_private", "system", death_msg, day, self.ticks_per_day)
                self.chat.send_message("ai_public", "system", death_msg, day, self.ticks_per_day)
                self._log_event("death", death_msg)

        # 存活统计
        alive = [a.name for a in self.agents.values() if a.alive]
        summary = f"📊 第{day+1}天结束，存活: {len(alive)}人 ({', '.join(alive)})"
        self.chat.send_message("ai_private", "system", summary, day, self.ticks_per_day)
        self._log_event("day_end", summary)

    async def _handle_decision(self, agent, decision_type, data, day, tick):
        """处理AI的决策"""
        if decision_type == "speak":
            room_id = data
            room = self.chat.rooms.get(room_id)
            if not room:
                return
            recent = self.chat.get_room_messages(room_id, 30)
            text, action = await agent.decide_action(room, self.chat, day, tick, recent)

            if text:
                self.chat.send_message(room_id, agent.name, text, day, tick)
                self._log_event("message", f"[{room.name}] {agent.name}: {text}")

            if action:
                await self._handle_action(agent, action, room_id, day, tick)

        elif decision_type == "create_chat":
            invite = data.get("invite", [])
            # 确保被邀请的人存在且存活
            invite = [n for n in invite if n in self.agents and self.agents[n].alive]
            if invite:
                members = [agent.name] + invite
                room = self.chat.create_room(agent.name, members)
                self.chat.send_message(
                    room.id, "system",
                    f"🔒 {agent.name}创建了私密聊天，成员: {', '.join(members)}",
                    day, tick
                )
                self._log_event("create_chat", f"{agent.name}创建私密群: {', '.join(members)}")

    async def _handle_action(self, agent, action, room_id, day, tick):
        """处理AI的具体动作"""
        act_type = action.get("action")

        if act_type == "trade_offer":
            target_name = action.get("target")
            if target_name not in self.agents or not self.agents[target_name].alive:
                return
            offer = action.get("offer", {})
            want = action.get("want", {})
            trade_id = f"trade_{len(self.pending_trades)}"
            self.pending_trades[trade_id] = {
                "from": agent.name,
                "to": target_name,
                "offer": offer,
                "want": want,
                "room_id": room_id,
                "status": "pending"
            }
            # 在聊天室通知
            msg = (f"💱 {agent.name}向{target_name}发起交易: "
                   f"给出{offer.get('cans',0)}罐头+{offer.get('water',0)}水, "
                   f"换取{want.get('cans',0)}罐头+{want.get('water',0)}水 "
                   f"[交易ID: {trade_id}]")
            self.chat.send_message(room_id, "system", msg, day, tick)
            self._log_event("trade_offer", msg)

            # 将交易加入目标AI的待处理列表
            self.agents[target_name].pending_trades.append(trade_id)

        elif act_type == "accept_trade":
            trade_id = action.get("trade_id")
            if trade_id in self.pending_trades:
                trade = self.pending_trades[trade_id]
                if trade["to"] == agent.name and trade["status"] == "pending":
                    from_agent = self.agents[trade["from"]]
                    success = from_agent.execute_trade(
                        agent,
                        give=trade["offer"],
                        receive=trade["want"]
                    )
                    trade["status"] = "completed" if success else "failed"
                    result = "✅ 交易成功" if success else "❌ 交易失败(资源不足)"
                    self.chat.send_message(trade["room_id"], "system",
                        f"{result}: {trade['from']}↔{trade['to']}", day, tick)
                    self._log_event("trade_result", f"{trade_id}: {result}")

                    # 更新关系
                    if success:
                        from_agent.update_relationship(agent.name, "完成交易", 10)
                        agent.update_relationship(from_agent.name, "完成交易", 10)

        elif act_type == "reject_trade":
            trade_id = action.get("trade_id")
            if trade_id in self.pending_trades:
                trade = self.pending_trades[trade_id]
                if trade["to"] == agent.name and trade["status"] == "pending":
                    trade["status"] = "rejected"
                    self.chat.send_message(trade["room_id"], "system",
                        f"🚫 {agent.name}拒绝了{trade['from']}的交易", day, tick)
                    self.agents[trade["from"]].update_relationship(agent.name, "拒绝交易", -5)

        elif act_type == "create_private_chat":
            invite = action.get("invite", [])
            invite = [n for n in invite if n in self.agents and self.agents[n].alive]
            if invite:
                members = [agent.name] + invite
                room = self.chat.create_room(agent.name, members)
                self.chat.send_message(room.id, "system",
                    f"🔒 {agent.name}创建了私密聊天", day, tick)
                self._log_event("create_chat", f"{agent.name}创建私密群: {', '.join(members)}")

        elif act_type == "eat":
            # 手动吃东西(提前消耗)
            pass  # 由end_day统一处理

    def human_send_message(self, room_id, content):
        """人类发送消息"""
        room = self.chat.rooms.get(room_id)
        if not room or not room.human_joined:
            return None
        return self.chat.send_message(room_id, "human", content,
                                       self.current_day, self.current_tick)

    def _end_simulation(self):
        """模拟结束"""
        alive = [a for a in self.agents.values() if a.alive]
        if alive:
            msg = f"🎉 救援到达！存活者: {', '.join(a.name for a in alive)}"
        else:
            msg = "💀 无人生还..."
        self.chat.send_message("ai_private", "system", msg, self.current_day, 0)
        self.chat.send_message("ai_public", "system", msg, self.current_day, 0)
        self._log_event("simulation_end", msg)
        self.running = False

    def _log_event(self, event_type, content):
        """记录事件"""
        event = {
            "type": event_type,
            "content": content,
            "day": self.current_day,
            "tick": self.current_tick,
            "timestamp": time.time()
        }
        self.event_log.append(event)
        if self.on_event:
            self.on_event(event)

    def get_state(self):
        """获取完整模拟状态"""
        return {
            "day": self.current_day,
            "tick": self.current_tick,
            "total_days": self.total_days,
            "running": self.running,
            "paused": self.paused,
            "agents": {name: a.get_status() for name, a in self.agents.items()},
            "rooms": {rid: r.to_dict() for rid, r in self.chat.rooms.items()},
            "resource_schedule": self.resource_mgr.get_schedule_info(),
            "recent_events": self.event_log[-50:]
        }