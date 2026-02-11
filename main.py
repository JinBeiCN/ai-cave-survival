import asyncio
from simulation import Simulation
from web_server import WebServer

async def main():
    print("=" * 60)
    print("  🏔️  AI山洞生存模拟器")
    print("=" * 60)

    # 加载模拟
    sim = Simulation("config.yaml")
    server = WebServer(sim, port=8080)

    print(f"📋 已加载 {len(sim.agents)} 个AI代理:")
    for name, agent in sim.agents.items():
        print(f"   - {name}: {agent.personality[:30]}...")
    print(f"📅 模拟天数: {sim.total_days}天")
    print(f"⏱️  Tick间隔: {sim.tick_interval}秒")
    print()

    # 并行启动服务器和模拟
    await asyncio.gather(
        server.start(),
        sim.start()
    )

if __name__ == "__main__":
    asyncio.run(main())