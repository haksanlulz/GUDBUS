"""/legal embed builder — the SJG game-aid notice must render verbatim."""

from __future__ import annotations

import re

import discord

from gurps_bot.cogs.legal import build_legal_embed

# discord renders [label](url) as just the label
_MD_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")

_FIELD_LIMIT = 1024
_EMBED_LIMIT = 6000

_AUTHOR = "Jane Q. Tester"
_INVITE = "https://discord.com/invite-sample"
_SUPPORT = "https://example.com/support-sample"

# SJG game-aid notice, verbatim — one character of drift is a compliance failure
_REQUIRED_NOTICE = (
    "GURPS is a trademark of Steve Jackson Games, and its rules and art are "
    "copyrighted by Steve Jackson Games. All rights are reserved by Steve "
    "Jackson Games. This game aid is the original creation of "
    f"{_AUTHOR} and is released for free distribution, and not for resale, "
    "under the permissions granted in the Steve Jackson Games Online Policy."
)


def test_privacy_notice_discloses_combat_and_discord_ids():
    embed = build_legal_embed(author=_AUTHOR, invite_url=None, support_url=None)
    privacy = next(f.value for f in embed.fields if f.name == "Privacy")
    assert "stores only" not in privacy.lower()  # no false closed-list claim
    assert "combat" in privacy.lower()
    assert "server" in privacy.lower() and "channel" in privacy.lower()


class TestAuthorResolution:
    """The notice credits the code's author. It defaults to the project's
    handle, so an instance that sets nothing still names the right person."""

    def test_defaults_to_the_project_handle(self, monkeypatch):
        from gurps_bot.cogs.legal import DEFAULT_AUTHOR, resolve_author
        monkeypatch.delenv("BOT_AUTHOR_NAME", raising=False)
        monkeypatch.delenv("BOT_AUTHOR_LEGAL_NAME", raising=False)
        assert resolve_author() == DEFAULT_AUTHOR == "haksanlulz"

    def test_bot_author_name_wins(self, monkeypatch):
        from gurps_bot.cogs.legal import resolve_author
        monkeypatch.setenv("BOT_AUTHOR_NAME", "Pen Name")
        monkeypatch.setenv("BOT_AUTHOR_LEGAL_NAME", "Old Name")
        assert resolve_author() == "Pen Name"

    def test_legacy_variable_still_honoured(self, monkeypatch):
        from gurps_bot.cogs.legal import resolve_author
        monkeypatch.delenv("BOT_AUTHOR_NAME", raising=False)
        monkeypatch.setenv("BOT_AUTHOR_LEGAL_NAME", "Old Name")
        assert resolve_author() == "Old Name"

    def test_blank_values_fall_through_to_the_default(self, monkeypatch):
        from gurps_bot.cogs.legal import DEFAULT_AUTHOR, resolve_author
        monkeypatch.setenv("BOT_AUTHOR_NAME", "  ")
        monkeypatch.setenv("BOT_AUTHOR_LEGAL_NAME", "")
        assert resolve_author() == DEFAULT_AUTHOR


class TestOperator:
    def test_hosted_by_shown_when_set(self):
        embed = build_legal_embed(
            author=_AUTHOR, invite_url=None, support_url=None, operator="Table Host",
        )
        assert "Hosted by Table Host" in _full_text(embed)

    def test_no_hosted_by_line_when_unset(self):
        embed = build_legal_embed(author=_AUTHOR, invite_url=None, support_url=None)
        assert "Hosted by" not in _full_text(embed)

_POLICY_URL = "https://www.sjgames.com/general/online_policy.html"


def _full_text(embed: discord.Embed) -> str:
    """all embed text, raw markdown (links not collapsed)."""
    parts: list[str] = []
    if embed.title:
        parts.append(embed.title)
    if embed.description:
        parts.append(embed.description)
    for field in embed.fields:
        parts.append(field.name or "")
        parts.append(field.value or "")
    if embed.footer and embed.footer.text:
        parts.append(embed.footer.text)
    return "\n".join(parts)


def _rendered_text(embed: discord.Embed) -> str:
    """text as displayed: markdown links collapsed — the verbatim check runs on this."""
    return _MD_LINK.sub(r"\1", _full_text(embed))


def _embed() -> discord.Embed:
    return build_legal_embed(author=_AUTHOR, invite_url=_INVITE, support_url=_SUPPORT)


class TestRequiredNotice:
    def test_verbatim_notice_present_exactly(self):
        # compliance is on the displayed form (link labels resolved)
        text = _rendered_text(_embed())
        assert _REQUIRED_NOTICE in text

    def test_author_is_substituted_from_argument(self):
        text = _rendered_text(_embed())
        assert _AUTHOR in text
        # the substitution token must not leak
        assert "{AUTHOR}" not in text

    def test_online_policy_url_present(self):
        text = _full_text(_embed())
        assert _POLICY_URL in text

    def test_online_policy_phrase_is_hyperlinked(self):
        text = _full_text(_embed())
        assert f"[Steve Jackson Games Online Policy]({_POLICY_URL})" in text


class TestAttribution:
    def test_gcs_master_library_credited(self):
        text = _full_text(_embed())
        assert "richardwilkes/gcs_master_library" in text
        assert "Richard A. Wilkes and contributors" in text

    def test_mpl_license_named(self):
        text = _full_text(_embed())
        assert "MPL-2.0" in text

    def test_gurpscharactersheet_linked(self):
        text = _full_text(_embed())
        assert "gurpscharactersheet.com" in text


class TestTrademark:
    def test_not_official_and_not_endorsed(self):
        text = _full_text(_embed()).lower()
        assert "not official" in text
        assert "not endorsed" in text

    def test_registered_trademark_statement(self):
        text = _full_text(_embed())
        assert "registered trademark of Steve Jackson Games" in text


class TestPrivacy:
    def test_does_not_read_message_content(self):
        text = _rendered_text(_embed()).lower()
        assert "does not read message content" in text

    def test_explains_removal_path(self):
        text = _full_text(_embed())
        assert "/char delete" in text
        assert "/privacy delete-my-data" in text

    def test_links_the_privacy_policy_and_terms(self):
        from gurps_bot.cogs.legal import DEFAULT_PRIVACY_URL, DEFAULT_TERMS_URL
        text = _full_text(_embed())
        assert DEFAULT_PRIVACY_URL in text
        assert DEFAULT_TERMS_URL in text

    def test_policy_urls_can_be_overridden(self):
        embed = build_legal_embed(
            author=_AUTHOR, invite_url=None, support_url=None,
            privacy_url="https://example.com/p", terms_url="https://example.com/t",
        )
        text = _full_text(embed)
        assert "https://example.com/p" in text and "https://example.com/t" in text


class TestContact:
    def test_invite_and_support_urls_present(self):
        text = _full_text(_embed())
        assert _INVITE in text
        assert _SUPPORT in text

    def test_missing_urls_render_placeholders_not_crash(self):
        embed = build_legal_embed(author=_AUTHOR, invite_url=None, support_url=None)
        assert _REQUIRED_NOTICE in _rendered_text(embed)


class TestDiscordCaps:
    def test_builds_an_embed(self):
        assert isinstance(_embed(), discord.Embed)

    def test_every_field_within_cap(self):
        for field in _embed().fields:
            assert len(field.value) <= _FIELD_LIMIT, field.name

    def test_total_embed_within_cap(self):
        assert len(_embed()) <= _EMBED_LIMIT

    def test_every_optional_field_set_stays_within_caps(self):
        embed = build_legal_embed(
            author="A Rather Long Pen Name For Cap Testing",
            invite_url=_INVITE,
            support_url=_SUPPORT,
            operator="A Rather Long Operator Name For Cap Testing",
        )
        assert len(embed) <= _EMBED_LIMIT
        for field in embed.fields:
            assert len(field.value) <= _FIELD_LIMIT, field.name
