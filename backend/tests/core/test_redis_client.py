import httpx
import pytest
from redis.asyncio import Redis

from app.core import redis as core_redis
from app.core.http_client import USER_AGENT, make_http_client
from tests.conftest import REDIS_URL, redis_db_index

pytestmark = pytest.mark.integration


async def test_client_lifecycle_and_json_helpers(redis: Redis) -> None:
    with pytest.raises(RuntimeError, match="not initialised"):
        core_redis.get_redis()
    core_redis.init_redis(f"{REDIS_URL}/{redis_db_index()}")
    try:
        await core_redis.ping_redis()
        await core_redis.set_json("j", {"a": [1, 2]}, ttl_s=60)
        assert await core_redis.get_json("j") == {"a": [1, 2]}
        assert await core_redis.get_json("missing") is None
        assert await redis.ttl("j") > 0
    finally:
        await core_redis.close_redis()
    await core_redis.close_redis()


async def test_http_client_defaults() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ua": request.headers["user-agent"]})

    async with make_http_client(transport=httpx.MockTransport(handler)) as client:
        assert client.follow_redirects is False
        assert (await client.get("https://x.test/")).json() == {"ua": USER_AGENT}
