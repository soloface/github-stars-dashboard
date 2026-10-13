"""Tests for scripts/translate_descriptions.py.

Stdlib unittest only. Network is stubbed via an injected ``opener`` so no real
Google request is made. Run:  python3 -m unittest tests.test_translate_descriptions -v
"""
import ast
import inspect
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from scripts import translate_descriptions as td  # noqa: E402

# The script pauses 0.3s after each real translation attempt. Tests never wait.
_ORIGINAL_SLEEP = td._sleep
td._sleep = lambda _seconds: None


class FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def google_response(*segments):
    """Build a payload shaped like the translate.googleapis.com reply."""
    return json.dumps([[list(seg) for seg in segments]]).encode()


class ContainsChineseTest(unittest.TestCase):
    def test_true_for_chinese(self):
        self.assertTrue(td.contains_chinese("一个仓库"))

    def test_false_for_english(self):
        self.assertFalse(td.contains_chinese("A repository"))

    def test_true_for_mixed(self):
        self.assertTrue(td.contains_chinese("hello 世界"))


class TranslateTest(unittest.TestCase):
    def test_parses_google_response(self):
        payload = google_response(["你好世界", "hello world", None, None, 10])
        out = td.translate("hello world", opener=lambda req: FakeResp(payload))
        self.assertEqual(out, "你好世界")

    def test_skips_mostly_chinese_input_without_network_call(self):
        def explode(req):
            raise AssertionError("opener must not be called for mostly-Chinese input")
        self.assertEqual(td.translate("已是中文", opener=explode), "已是中文")

    def test_mixed_below_ratio_still_calls_network(self):
        # Several ASCII words and one ideograph stay under the unit threshold.
        payload = google_response(["你好世界", "hello world", None, None, 1])
        out = td.translate("hello world 世", opener=lambda req: FakeResp(payload))
        self.assertEqual(out, "你好世界")

    def test_empty_returns_empty(self):
        self.assertEqual(td.translate("", opener=lambda req: FakeResp(b"[]")), "")

    def test_network_error_returns_none(self):
        def boom(req):
            raise RuntimeError("network down")
        self.assertIsNone(td.translate("hello", opener=boom))

    def test_bad_payload_returns_none(self):
        self.assertIsNone(td.translate("hello", opener=lambda req: FakeResp(b"not json")))


class DependencyTest(unittest.TestCase):
    def test_uses_only_stdlib_no_translator_package(self):
        src = inspect.getsource(td)
        for banned in ("deep_translator", "googletrans", "import requests", "from requests"):
            self.assertNotIn(banned, src)
        # HTTP must be done through the stdlib urllib, not a third-party client.
        self.assertIn("urllib", src)
        # every imported top-level module must resolve as a builtin/stdlib import
        tree = ast.parse(src)
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.level == 0:
                    names.add(node.module.split(".")[0])
        third_party = {"deep_translator", "googletrans", "requests", "httpx", "aiohttp"}
        self.assertFalse(names & third_party, "third-party deps found: %s" % (names & third_party))


class TranslateDescriptionsTest(unittest.TestCase):
    def _fake_translator(self):
        calls = []

        def fn(text):
            calls.append(text)
            return "译文:" + text

        fn.calls = calls
        return fn

    def test_populates_missing_description_zh(self):
        fn = self._fake_translator()
        repos = [{"description": "A repo"}, {"description": "Another"}]
        td.translate_descriptions(repos, translate_fn=fn)
        self.assertEqual(repos[0]["description_zh"], "译文:A repo")
        self.assertEqual(repos[1]["description_zh"], "译文:Another")

    def test_preserves_existing_translation(self):
        fn = self._fake_translator()
        repos = [{"description": "A repo", "description_zh": "已有译文"}]
        td.translate_descriptions(repos, translate_fn=fn)
        self.assertEqual(repos[0]["description_zh"], "已有译文")
        self.assertEqual(fn.calls, [], "must not re-translate when description_zh already set")

    def test_empty_description_yields_empty_translation(self):
        fn = self._fake_translator()
        repos = [{"description": ""}]
        td.translate_descriptions(repos, translate_fn=fn)
        self.assertEqual(repos[0]["description_zh"], "")

    def test_chinese_description_is_kept_as_is(self):
        fn = self._fake_translator()
        repos = [{"description": "中文简介"}]
        td.translate_descriptions(repos, translate_fn=fn)
        self.assertEqual(repos[0]["description_zh"], "中文简介")

    def test_file_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "stars.json")
            with open(path, "w") as f:
                json.dump([{"description": "hello"}, {"description": "中文"}], f)
            # A result with no ideographs is a failed translation and is not stored.
            td.process_file(path, translate_fn=lambda t: "译:" + t if t and not td.is_mostly_chinese(t) else t)
            with open(path) as f:
                result = json.load(f)
            self.assertEqual(result[0]["description_zh"], "译:hello")
            self.assertEqual(result[1]["description_zh"], "中文")


class DataPathTest(unittest.TestCase):
    def test_data_file_resolves_under_repo_root(self):
        expected = os.path.normpath(os.path.join(ROOT, "data", "stars.json"))
        self.assertEqual(os.path.normpath(td.DATA_FILE), expected)


# Descriptions copied from data/stars.json (full_name noted). Tests must not
# read that file; the strings are fixtures.
DESC_EASEL = (  # ZJU-REAL/Easel
    "An open-source AI agent for social media — discover trends, create content, "
    "publish everywhere, and learn what works across Xiaohongshu, Douyin, Zhihu, "
    "Bilibili, and more.🎨一个开源的 AI 社交媒体智能体——发现热点趋势、创作内容、"
    "一键发布至各大平台，并学习分析哪些内容真正有效，覆盖小红书、抖音、知乎、哔哩哔哩等平台。"
)
DESC_HTML = (  # QingYunA/answer-me-with-html
    "Answer me with HTML — an agent skill that answers hard questions with a "
    "one-page HTML you can actually read. 让 AI Agent 用一页 HTML 回答复杂问题。"
)
DESC_BUTTERFLY = (  # alibaba/butterfly
    "🦋Butterfly，A JavaScript/React/Vue2 Diagramming library which concentrate "
    "on flow layout field.    (基于JavaScript/React/Vue2的流程图组件)"
)
DESC_CODEX = (  # BigPizzaV3/CodexPlusPlus
    "An enhanced tool for CodexApp, striving to make Codex better to use and "
    "more comfortable 一个CodexApp的增强工具，努力让Codex变得更好用更舒服"
)
DESC_DENO = (  # tech-shrimp/deno-api-proxy
    "使用Deno将大模型的API 代理到国内，解决地区受限问题 Use Deno to proxy Open AI, "
    "Claude, Groq and other APIs to mainland China, breaking geographical restrictions."
)
DESC_VOYAGER = (  # voyager-crew/voyager
    "Enhancement suite for Gemini, AI Studio, Claude, ChatGPT & DeepSeek — plus "
    "a prompt manager for any website, DeepSeek Harness included. / 面向 Gemini、"
    "AI Studio、Claude、ChatGPT 与 DeepSeek 的增强套件；其中的提示词管理器可用于任意网站，"
    "如 DeepSeek Harness。"
)
DESC_SKILLS = (  # zhuyansen/awesome-claude-video-skills
    "Open-source skills and toolkits that let Claude Code, Codex and other coding "
    "agents make video. 180 repos by type, each security-graded. English / 中文."
)
DESC_LARK = (  # larksuite/cli
    "The official Lark/飞书 CLI tool, maintained by the larksuite team — built for "
    "humans and AI Agents. Covers core business domains including Messenger, Docs, "
    "Base, Sheets, Calendar, Mail, Tasks, Meetings, and more, with 200+ commands "
    "and 20+ AI Agent Skills."
)
DESC_LEMO = (  # lemomo-ai/lemo-opuscar
    "Claude Code skill for short films with no video model: 43 film styles, each "
    "a style prompt plus a demo film made entirely in code by Claude Opus 5.5 "
    "(incl. OPUSCAR 98). By Lemomo. · Opus5.5 x 43 种影片风格：风格提示词 + 纯代码样片 "
    "+ 导演与技术指南"
)

ZH_EASEL = (
    "一个开源的 AI 社交媒体智能体——发现热点趋势、创作内容、一键发布至各大平台，"
    "并学习分析哪些内容真正有效，覆盖小红书、抖音、知乎、哔哩哔哩等平台。"
)
ZH_HTML = "让 AI Agent 用一页 HTML 回答复杂问题。"
ZH_BUTTERFLY = "基于JavaScript/React/Vue2的流程图组件"
ZH_CODEX = "一个CodexApp的增强工具，努力让Codex变得更好用更舒服"
ZH_DENO = "使用Deno将大模型的API 代理到国内，解决地区受限问题"
ZH_VOYAGER = (
    "面向 Gemini、AI Studio、Claude、ChatGPT 与 DeepSeek 的增强套件；"
    "其中的提示词管理器可用于任意网站，如 DeepSeek Harness。"
)
ZH_LEMO = "Opus5.5 x 43 种影片风格：风格提示词 + 纯代码样片 + 导演与技术指南"

# More descriptions copied verbatim from data/stars.json. Tests must not read
# that file. full_name is only a comment.
DESC_AIMAMI = "为OpenAI Codex打造的桌面伴侣。"  # borawong/AiMaMi
DESC_TRENDRADAR = (  # sansan0/TrendRadar
    "⭐AI-driven public opinion & trend monitor with multi-platform aggregation, "
    "RSS, and smart alerts.🎯 告别信息过载，你的 AI 舆情监控助手与热点筛选工具！"
    "聚合多平台热点 +  RSS 订阅，支持关键词精准筛选。AI 智能筛选新闻 + AI 翻译 +  "
    "AI 分析简报直推手机，也支持接入 MCP 架构，赋能 AI 自然语言对话分析、情感洞察与趋势预测等。"
    "支持 Docker ，数据本地/云端自持。集成微信/飞书/钉钉/Telegram/邮件/ntfy/bark/slack 等渠道智能推送。"
)
DESC_HUMANIZER = (  # op7418/Humanizer-zh
    "Humanizer 的汉化版本，Claude Code Skills，旨在消除文本中 AI 生成的痕迹。"
)
DESC_OPENCLAW_LARK = "飞书官方出品的 OpenClaw 飞书/Lark Channel 插件"  # larksuite/openclaw-lark
DESC_RNSKILL = "雪踏乌云的 AI Agent Skills 集合"  # Pluviobyte/rnskill
DESC_CODEX2API = (  # james-6-23/codex2api
    "Codex2API 是一个基于 Go + Gin + React/Vite 的 Codex 反向代理与管理后台项目"
)
DESC_CHAT_GATEWAY = "OpenClaw 的聊天网关，摆脱对各种 Channel 的依赖"  # liandu2024/OpenClaw-Chat-Gateway
DESC_ALLINONE = (  # FanchangWang/allinone_format
    "本项目是对 https://hub.docker.com/r/youshandefeiyang/allinone /tv.m3u、"
    "/tptv.m3u、/migu.m3u 进行聚合 & 重新分组。"
)
DESC_GPT_IMAGE = (  # freestylefly/awesome-gpt-image-2
    "Prompt as Code | GPT Image 2 / 2.5 提示词与案例库，530+ 个案例、20+ 套工业级模板与可复用 "
    "Skills，新增 2.5 同提示词对比专区，附完整提示词与生成记录，持续更新。"
)
DESC_HUASHU = (  # alchaincyf/huashu-design
    "Huashu Design · HTML-native design skill for Claude Code · Claude Code 里 "
    "HTML 原生的设计 skill · 高保真原型 / 幻灯片 / 动画 + 20 设计哲学 + 5 维评审 + "
    "MP4 导出 · Agent-agnostic"
)
DESC_XIAOZHI = "An MCP-based chatbot | 一个基于MCP的聊天机器人"  # 78/xiaozhi-esp32

# is_mostly_chinese is True under the unit rule. tech-shrimp/deno-api-proxy is DESC_DENO.
MOSTLY_CHINESE_FIXTURES = (
    ("borawong/AiMaMi", DESC_AIMAMI),
    ("sansan0/TrendRadar", DESC_TRENDRADAR),
    ("op7418/Humanizer-zh", DESC_HUMANIZER),
    ("larksuite/openclaw-lark", DESC_OPENCLAW_LARK),
    ("Pluviobyte/rnskill", DESC_RNSKILL),
    ("james-6-23/codex2api", DESC_CODEX2API),
    ("liandu2024/OpenClaw-Chat-Gateway", DESC_CHAT_GATEWAY),
    ("FanchangWang/allinone_format", DESC_ALLINONE),
    ("freestylefly/awesome-gpt-image-2", DESC_GPT_IMAGE),
    ("alchaincyf/huashu-design", DESC_HUASHU),
    ("78/xiaozhi-esp32", DESC_XIAOZHI),
    ("tech-shrimp/deno-api-proxy", DESC_DENO),
)

# Still not mostly Chinese under the unit rule.
NOT_MOSTLY_CHINESE_FIXTURES = (
    ("QingYunA/answer-me-with-html", DESC_HTML),
    ("lemomo-ai/lemo-opuscar", DESC_LEMO),
    ("voyager-crew/voyager", DESC_VOYAGER),
    ("alibaba/butterfly", DESC_BUTTERFLY),
    ("larksuite/cli", DESC_LARK),
    ("zhuyansen/awesome-claude-video-skills", DESC_SKILLS),
)


class ChineseRatioTest(unittest.TestCase):
    def test_constant(self):
        self.assertEqual(td.ZH_RATIO, 0.5)

    def test_pure_chinese(self):
        self.assertEqual(td.chinese_ratio("完全是中文简介"), 1.0)
        self.assertTrue(td.is_mostly_chinese("完全是中文简介"))

    def test_pure_english(self):
        self.assertEqual(td.chinese_ratio("A repository of tools"), 0.0)
        self.assertFalse(td.is_mostly_chinese("A repository of tools"))

    def test_mostly_chinese_with_a_little_english(self):
        text = "基于 React 的组件库"
        # 基于的组件库 = 6 hanzi, React = 1 word.
        self.assertEqual(td.chinese_ratio(text), 6 / 7)
        self.assertTrue(td.is_mostly_chinese(text))

    def test_half_boundary_is_inclusive(self):
        # 1 hanzi + 1 word. "中文ab" is 2 hanzi + 1 word, not the boundary.
        self.assertEqual(td.chinese_ratio("中a"), 0.5)
        self.assertTrue(td.is_mostly_chinese("中a"))
        self.assertEqual(td.chinese_ratio("中文 ab cd"), 0.5)
        self.assertTrue(td.is_mostly_chinese("中文 ab cd"))
        # 1 hanzi + 2 words.
        self.assertEqual(td.chinese_ratio("中ab cd"), 1 / 3)
        self.assertFalse(td.is_mostly_chinese("中ab cd"))

    def test_desktop_companion_sentence_is_chinese(self):
        text = "为OpenAI Codex打造的桌面伴侣。"
        # 为打造的桌面伴侣 = 8 hanzi, OpenAI + Codex = 2 words. "。" is ignored.
        self.assertEqual(td.chinese_ratio(text), 8 / 10)
        self.assertTrue(td.is_mostly_chinese(text))

    def test_emoji_and_punctuation_are_ignored(self):
        self.assertEqual(td.chinese_ratio("中文！🎉"), 1.0)
        self.assertTrue(td.is_mostly_chinese("中文！🎉"))
        self.assertEqual(td.chinese_ratio("🎉！！"), 0.0)
        self.assertFalse(td.is_mostly_chinese("🎉！！"))
        self.assertEqual(td.chinese_ratio("中！a"), 0.5)
        # The dot splits the run: Opus5 and 5 are two words.
        self.assertEqual(td.chinese_ratio("种Opus5.5"), 1 / 3)

    def test_empty_string(self):
        self.assertEqual(td.chinese_ratio(""), 0.0)
        self.assertFalse(td.is_mostly_chinese(""))

    def test_whitespace_is_ignored(self):
        self.assertEqual(td.chinese_ratio("中 文"), 1.0)
        self.assertEqual(td.chinese_ratio("   "), 0.0)

    def test_extension_a_counts(self):
        ext = "\u3400" * 4
        self.assertEqual(td.chinese_ratio(ext), 1.0)
        self.assertTrue(td.is_mostly_chinese(ext))
        self.assertFalse(td.contains_chinese(ext))

    def test_looks_chinese_accepts_product_names(self):
        phrase = "面向 Gemini、AI Studio、Claude、ChatGPT 与 DeepSeek 的增强套件"
        # 面向与的增强套件 = 8 hanzi, 6 product words.
        self.assertEqual(td.chinese_ratio(phrase), 8 / 14)
        self.assertTrue(td.is_mostly_chinese(phrase))
        self.assertTrue(td.looks_chinese(phrase))
        # 基于的流程图组件 = 8 hanzi, JavaScript + React + Vue2 = 3 words.
        self.assertEqual(td.chinese_ratio(ZH_BUTTERFLY), 8 / 11)
        self.assertTrue(td.looks_chinese(ZH_BUTTERFLY))
        self.assertTrue(td.is_mostly_chinese(ZH_BUTTERFLY))
        # Dropping two ideographs puts the same clause under the unit threshold.
        sparse = "面向 Gemini、AI Studio、Claude、ChatGPT 与 DeepSeek 的套"
        self.assertLess(td.chinese_ratio(sparse), 0.5)
        self.assertFalse(td.is_mostly_chinese(sparse))
        self.assertTrue(td.looks_chinese(sparse))


class ExtractChineseSegmentTest(unittest.TestCase):
    def test_easel_keeps_internal_em_dash(self):
        got = td.extract_chinese_segment(DESC_EASEL)
        self.assertEqual(got, ZH_EASEL)
        self.assertIn("智能体——发现", got)

    def test_html_answer(self):
        self.assertEqual(td.extract_chinese_segment(DESC_HTML), ZH_HTML)

    def test_butterfly_strips_parens(self):
        self.assertEqual(td.extract_chinese_segment(DESC_BUTTERFLY), ZH_BUTTERFLY)

    def test_codex_space_boundary(self):
        self.assertEqual(td.extract_chinese_segment(DESC_CODEX), ZH_CODEX)

    def test_deno_chinese_then_english(self):
        self.assertEqual(td.extract_chinese_segment(DESC_DENO), ZH_DENO)

    def test_voyager_slash_and_product_names(self):
        got = td.extract_chinese_segment(DESC_VOYAGER)
        self.assertEqual(got, ZH_VOYAGER)
        self.assertTrue(td.looks_chinese(got))

    def test_short_chinese_tail_is_none(self):
        self.assertIsNone(td.extract_chinese_segment(DESC_SKILLS))

    def test_embedded_feishu_is_none(self):
        self.assertIsNone(td.extract_chinese_segment(DESC_LARK))

    def test_lemo_chinese_run_is_mostly_chinese(self):
        got = td.extract_chinese_segment(DESC_LEMO)
        self.assertEqual(got, ZH_LEMO)
        self.assertTrue(td.looks_chinese(got))
        self.assertGreaterEqual(td.hanzi_count(got), 4)
        self.assertIn("种影片风格", got)

    def test_alternating_languages_return_none(self):
        text = "This is an English sentence. 这是一段中文内容。 This is English again. 这是另一段中文。"
        self.assertIsNone(td.extract_chinese_segment(text))

    def test_pure_chinese_has_no_english_side(self):
        self.assertIsNone(td.extract_chinese_segment("这是一段完整的中文简介。"))

    def test_pure_english_is_none(self):
        self.assertIsNone(td.extract_chinese_segment("A plain English description of a tool."))


class ResolveZhTest(unittest.TestCase):
    def test_empty(self):
        def explode(text):
            raise AssertionError("translate must not be called")
        self.assertEqual(td.resolve_zh("", explode), ("", True))

    def test_pure_chinese_does_not_translate(self):
        def explode(text):
            raise AssertionError("translate must not be called")
        self.assertEqual(td.resolve_zh("中文简介", explode), ("中文简介", True))

    def test_mostly_chinese_with_english_token_is_kept(self):
        def explode(text):
            raise AssertionError("translate must not be called")
        text = "基于 React 的组件库"
        self.assertEqual(td.resolve_zh(text, explode), (text, True))

    def test_pure_english_calls_translate(self):
        calls = []

        def fn(text):
            calls.append(text)
            return "译文"

        self.assertEqual(td.resolve_zh("A repository", fn), ("译文", True))
        self.assertEqual(calls, ["A repository"])

    def test_bilingual_extracts_without_translate(self):
        def explode(text):
            raise AssertionError("translate must not be called")
        self.assertEqual(td.resolve_zh(DESC_HTML, explode), (ZH_HTML, True))
        # 18 hanzi and 17 ASCII words: the whole description is mostly Chinese,
        # but the English lead-in is long enough to keep only the Chinese tail.
        self.assertTrue(td.is_mostly_chinese(DESC_CODEX))
        self.assertEqual(td.resolve_zh(DESC_CODEX, explode), (ZH_CODEX, True))

    def test_leading_english_keeps_chinese_segment_without_translate(self):
        def explode(text):
            raise AssertionError("translate must not be called")

        easel_prefix = td.leading_english_prefix(DESC_EASEL)
        codex_prefix = td.leading_english_prefix(DESC_CODEX)
        self.assertIsNotNone(easel_prefix)
        self.assertIsNotNone(codex_prefix)
        self.assertGreaterEqual(len(easel_prefix), 20)
        self.assertGreaterEqual(len(codex_prefix), 20)
        self.assertIn("🎨", easel_prefix)
        self.assertFalse(any(td._is_hanzi(ch) for ch in easel_prefix))
        self.assertTrue(td.is_mostly_chinese(DESC_EASEL))
        self.assertEqual(
            td.resolve_zh(DESC_EASEL, explode),
            (
                "一个开源的 AI 社交媒体智能体——发现热点趋势、创作内容、"
                "一键发布至各大平台，并学习分析哪些内容真正有效，覆盖小红书、"
                "抖音、知乎、哔哩哔哩等平台。",
                True,
            ),
        )
        self.assertEqual(td.resolve_zh(DESC_EASEL, explode), (ZH_EASEL, True))
        self.assertEqual(
            td.resolve_zh(DESC_CODEX, explode),
            ("一个CodexApp的增强工具，努力让Codex变得更好用更舒服", True),
        )
        self.assertEqual(td.resolve_zh(DESC_CODEX, explode), (ZH_CODEX, True))

    def test_mostly_chinese_fixtures_resolve_to_original(self):
        def explode(text):
            raise AssertionError("translate must not be called")

        self.assertEqual(len(MOSTLY_CHINESE_FIXTURES), 12)
        for name, desc in MOSTLY_CHINESE_FIXTURES:
            self.assertEqual(td.resolve_zh(desc, explode), (desc, True), name)

    def test_english_lead_without_chinese_segment_translates(self):
        samples = (
            ("larksuite/cli", DESC_LARK),
            ("zhuyansen/awesome-claude-video-skills", DESC_SKILLS),
        )
        for name, desc in samples:
            calls = []

            def fn(text, _calls=calls):
                _calls.append(text)
                return "需要翻译的中文结果"

            self.assertIsNone(td.extract_chinese_segment(desc), name)
            self.assertEqual(
                td.resolve_zh(desc, fn), ("需要翻译的中文结果", True), name
            )
            self.assertEqual(calls, [desc], name)

    def test_short_english_prefix_does_not_trigger(self):
        def explode(text):
            raise AssertionError("translate must not be called")

        # "Huashu Design · " is 16 characters, under the 20-character opening.
        lead = "Huashu Design · "
        self.assertLess(len(lead.strip()), 20)
        desc = lead + "这是一段完整的中文设计说明，包含足够多的汉字。"
        self.assertTrue(td.is_mostly_chinese(desc))
        self.assertIsNone(td.leading_english_prefix(desc))
        self.assertIsNotNone(td.extract_chinese_segment(desc))
        self.assertEqual(td.resolve_zh(desc, explode), (desc, True))
        # Chinese first, or a short English name glued into a Chinese sentence.
        self.assertIsNone(td.leading_english_prefix(DESC_DENO))
        self.assertEqual(td.resolve_zh(DESC_DENO, explode), (DESC_DENO, True))
        self.assertIsNone(td.leading_english_prefix("Humanizer 的汉化版本，旨在消除痕迹。"))
        self.assertEqual(
            td.resolve_zh(DESC_HUMANIZER, explode), (DESC_HUMANIZER, True)
        )

    def test_failures(self):
        desc = "A repository of tools"

        def raise_fn(text):
            raise RuntimeError("down")

        self.assertEqual(td.resolve_zh(desc, raise_fn), (None, False))
        self.assertEqual(td.resolve_zh(desc, lambda text: text), (None, False))
        self.assertEqual(td.resolve_zh(desc, lambda text: ""), (None, False))
        self.assertEqual(td.resolve_zh(desc, lambda text: None), (None, False))
        self.assertEqual(td.resolve_zh(desc, lambda text: "still english"), (None, False))


class TranslateDescriptionsBehaviorTest(unittest.TestCase):
    def test_failure_omits_field_and_retries(self):
        calls = []

        def fn(text):
            calls.append(text)
            if len(calls) == 1:
                raise RuntimeError("network down")
            return "成功译文"

        repos = [{"full_name": "a/a", "description": "Hello world"}]
        td.translate_descriptions(repos, translate_fn=fn)
        self.assertNotIn("description_zh", repos[0])
        self.assertEqual(td.stats["failed"], 1)
        td.translate_descriptions(repos, translate_fn=fn)
        self.assertEqual(repos[0]["description_zh"], "成功译文")
        self.assertEqual(calls, ["Hello world", "Hello world"])

    def test_failure_values_do_not_write(self):
        desc = "Hello world"
        for result in (desc, "", None, "still english"):
            repos = [{"description": desc}]
            td.translate_descriptions(repos, translate_fn=lambda text, result=result: result)
            self.assertNotIn("description_zh", repos[0])
            self.assertEqual(td.stats["failed"], 1)

    def test_default_skips_copied_english(self):
        calls = []
        desc = "Hello world"
        repos = [{"description": desc, "description_zh": desc}]
        td.translate_descriptions(repos, translate_fn=lambda text: calls.append(text) or "译文")
        self.assertEqual(repos[0]["description_zh"], desc)
        self.assertEqual(calls, [])

    def test_recheck_mixed_scope(self):
        calls = []
        english = "A plain English description"
        pure = "中文简介内容"
        repos = [
            {"full_name": "en/copy", "description": english, "description_zh": english},
            {"full_name": "en/done", "description": english, "description_zh": "已有译文"},
            {"full_name": "zh/pure", "description": pure, "description_zh": pure},
            {"full_name": "bi/mix", "description": DESC_HTML, "description_zh": DESC_HTML},
        ]

        def fn(text):
            calls.append(text)
            return "译:" + text

        td.translate_descriptions(repos, translate_fn=fn, recheck_mixed=True)
        self.assertEqual(repos[0]["description_zh"], "译:" + english)
        self.assertEqual(repos[1]["description_zh"], "已有译文")
        self.assertEqual(repos[2]["description_zh"], pure)
        self.assertEqual(repos[3]["description_zh"], ZH_HTML)
        self.assertEqual(calls, [english])

    def test_recheck_failure_keeps_old_value(self):
        desc = "A plain English description"
        repos = [{"description": desc, "description_zh": desc}]

        def fn(text):
            raise OSError("down")

        td.translate_descriptions(repos, translate_fn=fn, recheck_mixed=True)
        self.assertEqual(repos[0]["description_zh"], desc)
        self.assertEqual(td.stats["failed"], 1)
        self.assertEqual(td.stats["updated"], 0)

    def test_only_filters(self):
        calls = []
        repos = [
            {"full_name": "a/a", "description": "Hello"},
            {"full_name": "b/b", "description": "World"},
        ]

        def fn(text):
            calls.append(text)
            return "译:" + text

        td.translate_descriptions(repos, translate_fn=fn, only={"b/b"})
        self.assertNotIn("description_zh", repos[0])
        self.assertEqual(repos[1]["description_zh"], "译:World")
        self.assertEqual(calls, ["World"])

    def test_sleep_only_when_translate_is_called(self):
        pauses = []
        original = td._sleep
        td._sleep = pauses.append
        try:
            td.translate_descriptions(
                [{"description": "中文简介"}], translate_fn=lambda text: "不应该"
            )
            self.assertEqual(pauses, [])
            td.translate_descriptions(
                [{"description": DESC_HTML}], translate_fn=lambda text: "不应该"
            )
            self.assertEqual(pauses, [])
            td.translate_descriptions(
                [{"description": "Hello"}], translate_fn=lambda text: "你好"
            )
            self.assertEqual(pauses, [0.3])
            td.translate_descriptions(
                [{"description": "Hello again"}],
                translate_fn=lambda text: (_ for _ in ()).throw(RuntimeError("x")),
            )
            self.assertEqual(pauses, [0.3, 0.3])
        finally:
            td._sleep = original

    def test_sleep_hook_defaults_to_time_sleep(self):
        import time
        self.assertIs(_ORIGINAL_SLEEP, time.sleep)


class ProcessFileFormatTest(unittest.TestCase):
    def test_unchanged_file_is_not_rewritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "stars.json")
            raw = '[{"description": "Hello", "description_zh": "你好"}]'
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(raw)
            before = os.stat(path).st_mtime_ns

            def explode(text):
                raise AssertionError("translate must not be called")

            td.process_file(path, translate_fn=explode)
            with open(path, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), raw)
            self.assertEqual(os.stat(path).st_mtime_ns, before)

    def test_write_preserves_trailing_newline_and_unicode(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "stars.json")
            repos = [{"full_name": "a/a", "description": "Hello"}, {"full_name": "b/b", "description": "中文简介"}]
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(repos, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
            td.process_file(path, translate_fn=lambda text: "你好呀")
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            self.assertTrue(text.endswith("\n"))
            self.assertNotIn("\\u", text)
            loaded = json.loads(text)
            self.assertEqual(loaded[0]["description_zh"], "你好呀")
            self.assertEqual(loaded[1]["description_zh"], "中文简介")
            self.assertTrue(text.startswith("[\n  {"))

    def test_write_omits_newline_when_original_has_none(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "stars.json")
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write('[{"description": "Hello"}]')
            td.process_file(path, translate_fn=lambda text: "你好")
            with open(path, "rb") as handle:
                raw = handle.read()
            self.assertFalse(raw.endswith(b"\n"))
            self.assertIn("你好".encode("utf-8"), raw)
            loaded = json.loads(raw.decode("utf-8"))
            self.assertEqual(loaded[0]["description_zh"], "你好")


class MainDryRunTest(unittest.TestCase):
    def test_dry_run_does_not_write_or_translate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "stars.json")
            repos = [
                {"full_name": "a/a", "description": DESC_HTML, "description_zh": DESC_HTML},
                {"full_name": "b/b", "description": "A plain English description", "description_zh": "A plain English description"},
                {"full_name": "c/c", "description": "中文简介", "description_zh": "中文简介"},
            ]
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(repos, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
            with open(path, encoding="utf-8") as handle:
                before = handle.read()
            mtime = os.stat(path).st_mtime_ns

            def explode(text, opener=None):
                raise AssertionError("dry-run must not translate")

            saved_path = td.DATA_FILE
            saved_translate = td.translate
            try:
                td.DATA_FILE = path
                td.translate = explode
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    td.main(["--recheck-mixed", "--dry-run"])
            finally:
                td.DATA_FILE = saved_path
                td.translate = saved_translate
            with open(path, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), before)
            self.assertEqual(os.stat(path).st_mtime_ns, mtime)
            out = buffer.getvalue()
            self.assertIn("a/a", out)
            self.assertIn("extracted", out)
            self.assertIn(ZH_HTML, out)
            self.assertIn("b/b", out)
            self.assertIn("needs-translation", out)
            self.assertNotIn("c/c", out)


class FixtureChineseRatioTest(unittest.TestCase):
    def test_mostly_chinese_fixtures(self):
        for name, desc in MOSTLY_CHINESE_FIXTURES:
            self.assertTrue(td.is_mostly_chinese(desc), name)
            self.assertGreaterEqual(td.chinese_ratio(desc), td.ZH_RATIO, name)

    def test_recheck_mixed_keeps_copies_and_does_not_translate(self):
        calls = []
        repos = [
            {"full_name": name, "description": desc, "description_zh": desc}
            for name, desc in MOSTLY_CHINESE_FIXTURES
        ]

        def fn(text):
            calls.append(text)
            return "不应翻译:" + text

        td.translate_descriptions(repos, translate_fn=fn, recheck_mixed=True)
        self.assertEqual(calls, [])
        for repo, (name, desc) in zip(repos, MOSTLY_CHINESE_FIXTURES):
            self.assertEqual(repo["description_zh"], desc, name)
        self.assertEqual(td.stats["updated"], 0)
        self.assertEqual(td.stats["failed"], 0)
        self.assertEqual(td.stats["unchanged"], len(MOSTLY_CHINESE_FIXTURES))

    def test_not_mostly_chinese_fixtures(self):
        for name, desc in NOT_MOSTLY_CHINESE_FIXTURES:
            self.assertFalse(td.is_mostly_chinese(desc), name)
            self.assertLess(td.chinese_ratio(desc), td.ZH_RATIO, name)

    def test_two_bilingual_fixtures_are_mostly_chinese_by_units(self):
        # These were expected to stay non-Chinese. The unit rule does not
        # agree; the counts are locked here and reported, not forced under 0.5.
        cases = (
            ("ZJU-REAL/Easel", DESC_EASEL, 60, 26),
            ("BigPizzaV3/CodexPlusPlus", DESC_CODEX, 18, 17),
        )
        for name, desc, hanzi, words in cases:
            self.assertEqual(td.hanzi_count(desc), hanzi, name)
            self.assertEqual(len(td._ASCII_WORD_RE.findall(desc)), words, name)
            self.assertEqual(td.chinese_ratio(desc), hanzi / (hanzi + words), name)
            self.assertTrue(td.is_mostly_chinese(desc), name)


if __name__ == "__main__":
    unittest.main()
