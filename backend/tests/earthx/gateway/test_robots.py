"""robots.txt after RFC 9309: the parser alone, and the gateway that asks it (M5-18 §3.3)."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from earthx.gateway import HostResting, Policy, RobotsDisallowed, RobotsRules, UrlRejected
from earthx.gateway.client import Gateway
from earthx.gateway.robots import MAX_ROBOTS_BYTES

HOST = "catalog.example.org"
OTHER = "mirror.example.net"
AGENT = "EarthX/0.1 (+https://github.com/oscipal/earthX)"

pytestmark = pytest.mark.anyio


def rules(text: str, product: str = "EarthX") -> RobotsRules:
    return RobotsRules.parse(text.encode(), product)


class TestParser:
    def test_our_group_wins_over_the_star_group(self) -> None:
        parsed = rules("User-agent: *\nDisallow: /\n\nUser-agent: earthx\nDisallow: /private\n")
        assert parsed.allows("/collections")
        assert not parsed.allows("/private/x")

    def test_the_star_group_applies_without_ours(self) -> None:
        parsed = rules("User-agent: OtherBot\nDisallow: /\n\nUser-agent: *\nDisallow: /search\n")
        assert parsed.allows("/collections")
        assert not parsed.allows("/search?q=1")

    def test_no_matching_group_allows_everything(self) -> None:
        assert rules("User-agent: OtherBot\nDisallow: /\n").allows("/anything")

    def test_two_groups_for_us_are_merged(self) -> None:
        parsed = rules("User-agent: EarthX\nDisallow: /a\n\nUser-agent: EARTHX\nDisallow: /b\n")
        assert not parsed.allows("/a")
        assert not parsed.allows("/b")

    def test_consecutive_agent_lines_share_one_group(self) -> None:
        parsed = rules("User-agent: OtherBot\nUser-agent: EarthX\nDisallow: /x\n")
        assert not parsed.allows("/x")

    def test_the_longest_rule_decides(self) -> None:
        parsed = rules("User-agent: *\nDisallow: /data\nAllow: /data/public\n")
        assert parsed.allows("/data/public/x")
        assert not parsed.allows("/data/private")

    def test_allow_wins_a_tie(self) -> None:
        assert rules("User-agent: *\nDisallow: /page\nAllow: /page\n").allows("/page")

    def test_star_and_dollar_in_paths(self) -> None:
        parsed = rules("User-agent: *\nDisallow: /*.json$\nDisallow: /tmp*/cache\n")
        assert not parsed.allows("/a/b.json")
        assert parsed.allows("/a/b.json?x=1")
        assert not parsed.allows("/tmp-1/cache/z")

    def test_percent_encoding_compares_in_one_spelling(self) -> None:
        parsed = rules("User-agent: *\nDisallow: /karte/über\nDisallow: /a%3cb\n")
        assert not parsed.allows("/karte/%C3%BCber")
        assert not parsed.allows("/a%3Cb")

    def test_an_empty_disallow_allows_everything(self) -> None:
        assert rules("User-agent: *\nDisallow:\n").allows("/x")

    def test_comments_unknown_lines_and_sitemaps_are_skipped(self) -> None:
        text = "# hello\nSitemap: https://x/s.xml\nUser-agent: * # all\nNoise\nFoo: bar\nDisallow: /x # no\n"
        assert not rules(text).allows("/x")

    def test_rules_before_any_agent_line_belong_to_no_group(self) -> None:
        assert rules("Disallow: /\nUser-agent: OtherBot\n").allows("/x")

    def test_robots_txt_itself_is_never_disallowed(self) -> None:
        assert rules("User-agent: *\nDisallow: /\n").allows("/robots.txt")

    def test_an_empty_file_allows_everything(self) -> None:
        assert RobotsRules.parse(b"", "EarthX").allows("/x")

    def test_binary_garbage_does_not_crash(self) -> None:
        assert RobotsRules.parse(bytes(range(256)) * 4, "EarthX").allows("/x")

    def test_only_the_first_500_kib_count(self) -> None:
        padding = b"# " + b"x" * MAX_ROBOTS_BYTES + b"\n"
        parsed = RobotsRules.parse(b"User-agent: *\nDisallow: /a\n" + padding + b"Disallow: /b\n", "EarthX")
        assert not parsed.allows("/a")
        assert parsed.allows("/b")

    @pytest.mark.parametrize(("value", "delay"), [("2", 2.0), ("0.5", 0.5), ("soon", None), ("-3", None)])
    def test_crawl_delay(self, value: str, delay: float | None) -> None:
        assert rules(f"User-agent: *\nCrawl-delay: {value}\n").crawl_delay == delay


def public(host: str, port: int) -> tuple[str, ...]:
    return ("93.184.216.34",)


class Source:
    """Answers robots.txt per host as configured and records every request."""

    def __init__(self, robots: dict[str, httpx.Response | Exception]) -> None:
        self.robots = robots
        self.seen: list[str] = []
        self.now = 0.0

    def handle(self, request: httpx.Request) -> httpx.Response:
        host = request.headers["host"]
        self.seen.append(f"{host}{request.url.raw_path.decode()}")
        if request.url.path == "/robots.txt":
            answer = self.robots[host]
            if isinstance(answer, Exception):
                raise answer
            return answer
        return httpx.Response(200, json={})

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += seconds
        await asyncio.sleep(0)

    def gateway(self, policy: Policy) -> Gateway:
        return Gateway(
            policy, transport=httpx.MockTransport(self.handle), resolve=public, sleep=self.sleep, clock=self.clock
        )


def obeying(*hosts: str, **limits: object) -> Policy:
    return Policy(allowed_hosts=frozenset(hosts or {HOST}), user_agent=AGENT, obey_robots=True, **limits)  # type: ignore[arg-type]


def text(body: str) -> httpx.Response:
    return httpx.Response(200, text=body)


class TestGateway:
    async def test_a_disallowed_path_is_never_requested(self) -> None:
        source = Source({HOST: text("User-agent: EarthX\nDisallow: /private\n")})
        async with source.gateway(obeying()) as gateway:
            with pytest.raises(RobotsDisallowed) as raised:
                await gateway.get(f"https://{HOST}/private/x", params={"bbox": "1,2,3,4"})
            await gateway.get(f"https://{HOST}/collections")
        assert source.seen == [f"{HOST}/robots.txt", f"{HOST}/collections"]
        assert isinstance(raised.value, UrlRejected)
        assert "private" not in str(raised.value)
        assert "bbox" not in str(raised.value)

    async def test_the_query_counts_for_the_rule(self) -> None:
        source = Source({HOST: text("User-agent: *\nDisallow: /search?*page=\n")})
        async with source.gateway(obeying()) as gateway:
            with pytest.raises(RobotsDisallowed):
                await gateway.get(f"https://{HOST}/search", params={"q": "x", "page": "2"})
            await gateway.get(f"https://{HOST}/search", params={"q": "x"})

    async def test_robots_txt_is_read_once_per_host(self) -> None:
        source = Source({HOST: text("User-agent: *\nAllow: /\n")})
        async with source.gateway(obeying()) as gateway:
            await asyncio.gather(*(gateway.get(f"https://{HOST}/{index}") for index in range(4)))
        assert source.seen.count(f"{HOST}/robots.txt") == 1

    async def test_after_24_hours_it_is_read_again(self) -> None:
        source = Source({HOST: text("User-agent: *\nAllow: /\n")})
        async with source.gateway(obeying()) as gateway:
            await gateway.get(f"https://{HOST}/a")
            source.now += 24 * 3600
            await gateway.get(f"https://{HOST}/b")
        assert source.seen.count(f"{HOST}/robots.txt") == 2

    @pytest.mark.parametrize("status", [401, 403, 404, 410])
    async def test_a_4xx_allows_everything(self, status: int) -> None:
        source = Source({HOST: httpx.Response(status)})
        async with source.gateway(obeying()) as gateway:
            await gateway.get(f"https://{HOST}/anything")
        assert source.seen[-1] == f"{HOST}/anything"

    @pytest.mark.parametrize(
        "answer",
        [
            pytest.param(httpx.Response(429), id="429"),
            pytest.param(httpx.Response(500), id="500"),
            pytest.param(httpx.Response(503), id="503"),
            pytest.param(httpx.ReadTimeout("slow"), id="timeout"),
            pytest.param(httpx.ConnectError("refused"), id="unreachable"),
            pytest.param(httpx.Response(302), id="redirect-without-location"),
            pytest.param(httpx.Response(302, headers={"location": "https://elsewhere.example.com/r"}), id="off-list"),
        ],
    )
    async def test_an_unreadable_robots_txt_lets_the_host_rest(self, answer: httpx.Response | Exception) -> None:
        source = Source({HOST: answer})
        async with source.gateway(obeying()) as gateway:
            for _ in range(2):
                with pytest.raises(HostResting) as raised:
                    await gateway.get(f"https://{HOST}/collections")
        assert source.seen == [f"{HOST}/robots.txt"]
        assert raised.value.host == HOST
        assert "collections" not in str(raised.value)

    async def test_more_redirects_than_the_limit_let_the_host_rest(self) -> None:
        loop = httpx.Response(302, headers={"location": f"https://{HOST}/robots.txt"})
        source = Source({HOST: loop})
        async with source.gateway(obeying()) as gateway:
            with pytest.raises(HostResting):
                await gateway.get(f"https://{HOST}/collections")

    async def test_a_resting_host_does_not_stop_another(self) -> None:
        source = Source({HOST: httpx.Response(500), OTHER: text("")})
        async with source.gateway(obeying(HOST, OTHER)) as gateway:
            with pytest.raises(HostResting):
                await gateway.get(f"https://{HOST}/a")
            await gateway.get(f"https://{OTHER}/a")
        assert source.seen[-1] == f"{OTHER}/a"

    async def test_every_redirect_hop_is_asked(self) -> None:
        source = Source({HOST: text(""), OTHER: text("User-agent: *\nDisallow: /blocked\n")})

        def handle(request: httpx.Request) -> httpx.Response:
            if request.headers["host"] == HOST and request.url.path == "/moved":
                source.seen.append(f"{HOST}/moved")
                return httpx.Response(302, headers={"location": f"https://{OTHER}/blocked"})
            return source.handle(request)

        policy = obeying(HOST, OTHER)
        gateway = Gateway(policy, transport=httpx.MockTransport(handle), resolve=public, sleep=source.sleep)
        async with gateway:
            with pytest.raises(RobotsDisallowed):
                await gateway.get(f"https://{HOST}/moved")
        assert f"{OTHER}/blocked" not in source.seen

    async def test_a_crawl_delay_raises_the_spacing(self) -> None:
        source = Source({HOST: text("User-agent: *\nCrawl-delay: 5\n")})
        starts: list[float] = []
        original = source.handle

        def handle(request: httpx.Request) -> httpx.Response:
            if request.url.path != "/robots.txt":
                starts.append(source.now)
            return original(request)

        gateway = Gateway(
            obeying(min_interval_s=1.0),
            transport=httpx.MockTransport(handle),
            resolve=public,
            sleep=source.sleep,
            clock=source.clock,
        )
        async with gateway:
            await gateway.get(f"https://{HOST}/a")
            await gateway.get(f"https://{HOST}/b")
        assert starts[1] - starts[0] >= 5.0

    async def test_a_crawl_delay_above_30_s_lets_the_host_rest(self) -> None:
        source = Source({HOST: text("User-agent: *\nCrawl-delay: 120\n")})
        async with source.gateway(obeying()) as gateway:
            with pytest.raises(HostResting):
                await gateway.get(f"https://{HOST}/a")

    async def test_robots_txt_goes_out_with_our_user_agent(self) -> None:
        agents: list[str] = []

        def handle(request: httpx.Request) -> httpx.Response:
            agents.append(request.headers["user-agent"])
            return httpx.Response(200, text="")

        gateway = Gateway(obeying(), transport=httpx.MockTransport(handle), resolve=public)
        async with gateway:
            await gateway.get(f"https://{HOST}/a")
        assert agents == [AGENT, AGENT]

    async def test_without_the_switch_robots_txt_is_never_asked(self) -> None:
        source = Source({HOST: text("User-agent: *\nDisallow: /\n")})
        policy = Policy(allowed_hosts=frozenset({HOST}), user_agent=AGENT)
        async with source.gateway(policy) as gateway:
            await gateway.get(f"https://{HOST}/a")
            await gateway.head(f"https://{HOST}/b")
        assert source.seen == [f"{HOST}/a", f"{HOST}/b"]

    async def test_within_cannot_switch_robots_txt_off(self) -> None:
        source = Source({HOST: text("User-agent: *\nDisallow: /\n")})
        narrower = Policy(allowed_hosts=frozenset({HOST}), user_agent=AGENT)
        async with source.gateway(obeying()) as gateway:
            with pytest.raises(RobotsDisallowed):
                await gateway.head(f"https://{HOST}/a", within=narrower)
