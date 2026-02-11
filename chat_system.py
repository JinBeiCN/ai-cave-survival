import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class Message:
    """聊天消息"""
    id: str
    chat_id: str
    sender: str           # AI名字 / "system" / "human"
    content: str
    timestamp: float
    day: int
    tick: int
    visible_to_human: bool = True  # 用户是否可见(始终True, AI不知道)

    def to_dict(self):
        return {
            "id": self.id,
            "chat_id": self.chat_id,
            "sender": self.sender,
            "content": self.content,
            "timestamp": self.timestamp,
            "day": self.day,
            "tick": self.tick
        }

@dataclass
class ChatRoom:
    """聊天室"""
    id: str
    name: str
    members: list                    # AI成员名字列表
    human_joined: bool = False       # 人类是否被邀请加入
    human_aware: bool = False        # AI是否知道人类在看
    created_by: Optional[str] = None # 创建者
    messages: list = field(default_factory=list)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "members": self.members,
            "human_joined": self.human_joined,
            "human_aware": self.human_aware,
            "created_by": self.created_by,
            "message_count": len(self.messages)
        }


class ChatSystem:
    """聊天系统 - 管理所有聊天室和消息"""

    def __init__(self):
        self.rooms: dict[str, ChatRoom] = {}
        self.all_messages: list[Message] = []
        self._create_default_rooms()

    def _create_default_rooms(self):
        """创建默认聊天室"""
        # AI私密群聊(AI以为人类看不到)
        self.ai_private = ChatRoom(
            id="ai_private",
            name="山洞生存群(AI私密)",
            members=[],
            human_joined=False,
            human_aware=False,
            created_by="system"
        )
        self.rooms["ai_private"] = self.ai_private

        # 公开群聊(AI知道人类可以看到)
        self.ai_public = ChatRoom(
            id="ai_public",
            name="山洞生存群(公开)",
            members=[],
            human_joined=True,
            human_aware=True,
            created_by="system"
        )
        self.rooms["ai_public"] = self.ai_public

    def add_agent_to_defaults(self, agent_name):
        """将AI加入默认群聊"""
        if agent_name not in self.ai_private.members:
            self.ai_private.members.append(agent_name)
        if agent_name not in self.ai_public.members:
            self.ai_public.members.append(agent_name)

    def create_room(self, creator, members, name=None):
        """AI创建私密群聊"""
        room_id = f"room_{uuid.uuid4().hex[:8]}"
        if not name:
            name = f"{creator}的私密群({', '.join(members)})"
        room = ChatRoom(
            id=room_id,
            name=name,
            members=members,
            human_joined=False,
            human_aware=False,
            created_by=creator
        )
        self.rooms[room_id] = room
        return room

    def send_message(self, chat_id, sender, content, day, tick):
        """发送消息"""
        if chat_id not in self.rooms:
            return None
        msg = Message(
            id=uuid.uuid4().hex,
            chat_id=chat_id,
            sender=sender,
            content=content,
            timestamp=time.time(),
            day=day,
            tick=tick
        )
        self.rooms[chat_id].messages.append(msg)
        self.all_messages.append(msg)
        return msg

    def get_room_messages(self, chat_id, limit=50):
        """获取聊天室最近消息"""
        if chat_id not in self.rooms:
            return []
        return self.rooms[chat_id].messages[-limit:]

    def get_rooms_for_agent(self, agent_name):
        """获取AI可见的聊天室"""
        return {
            rid: room for rid, room in self.rooms.items()
            if agent_name in room.members
        }

    def get_all_rooms_for_human(self):
        """获取人类可见的所有聊天室(全部)"""
        return self.rooms

    def get_rooms_human_can_speak(self):
        """获取人类可以发言的聊天室"""
        return {
            rid: room for rid, room in self.rooms.items()
            if room.human_joined
        }