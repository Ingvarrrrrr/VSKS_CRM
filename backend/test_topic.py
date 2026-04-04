import asyncio
import httpx

TOKEN = "8688107013:AAFOibeJGHUFz1lJWK9bs0rFx2P1f7rTPac"
CHAT_ID = -1003768051281
API = f"https://api.telegram.org/bot{TOKEN}"


async def main():
    async with httpx.AsyncClient(timeout=10) as client:
        # 1. Create topic
        resp = await client.post(f"{API}/createForumTopic", json={
            "chat_id": CHAT_ID,
            "name": "Тестовая задача из CRM",
        })
        print(f"createForumTopic: {resp.status_code}")
        print(resp.text[:300])

        if resp.status_code == 200:
            topic_id = resp.json()["result"]["message_thread_id"]
            print(f"Topic ID: {topic_id}")

            # 2. Send message into topic
            link = '<a href="http://85.239.53.155/tasks">Перейти к задаче</a>'
            text = f"Задача создана в CRM\n{link}"
            resp2 = await client.post(f"{API}/sendMessage", json={
                "chat_id": CHAT_ID,
                "message_thread_id": topic_id,
                "text": text,
                "parse_mode": "HTML",
            })
            print(f"sendMessage: {resp2.status_code}")
            print(resp2.text[:200])


asyncio.run(main())
