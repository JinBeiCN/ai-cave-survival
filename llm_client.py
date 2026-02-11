import asyncio
import json
import re
from openai import AsyncOpenAI

class LLMClient:
    """LLM调用客户端"""

    def __init__(self, config):
        self.config = config
        params = {"api_key": config["api_key"]}
        if config.get("base_url"):
            params["base_url"] = config["base_url"]
        self.client = AsyncOpenAI(**params)
        self.model = config["model"]

    async def chat(self, system_prompt, messages, temperature=0.9):
        """调用LLM获取回复"""
        formatted = [{"role": "system", "content": system_prompt}]
        for msg in messages:
            formatted.append({"role": msg["role"], "content": msg["content"]})
        try:
            resp = await self.client.chat.completions.create(
                model=self.model,
                messages=formatted,
                temperature=temperature,
                max_tokens=2048
            )
            return resp.choices[0].message.content
        except Exception as e:
            print(f"LLM调用失败: {e}")
            return None

    async def structured_chat(self, system_prompt, messages, temperature=0.9):
        """调用LLM获取结构化JSON回复"""
        formatted = [{"role": "system", "content": system_prompt}]
        for msg in messages:
            formatted.append({"role": msg["role"], "content": msg["content"]})
        try:
            resp = await self.client.chat.completions.create(
                model=self.model,
                messages=formatted,
                temperature=temperature,
                max_tokens=2048
            )
            text = resp.choices[0].message.content
            # 提取JSON
            match = re.search(r'\{[\s\S]*\}', text)
            if match:
                return json.loads(match.group())
            return None
        except Exception as e:
            print(f"LLM结构化调用失败: {e}")
            return None