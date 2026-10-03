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


def test_unset_author_renders_loud_non_compliant_marker():
    from gurps_bot.cogs.legal import _AUTHOR_PLACEHOLDER
    assert "CONFIG REQUIRED" in _AUTHOR_PLACEHOLDER
    assert "BOT_AUTHOR_LEGAL_NAME" in _AUTHOR_PLACEHOLDER
    embed = build_legal_embed(author=_AUTHOR_PLACEHOLDER, invite_url=None, support_url=None)
    text = "\n".join(f.value for f in embed.fields)
    assert "not" in text.lower() and "compliant" in text.lower()

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
        assert "Richard Wilkes" in text

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

    def test_default_author_placeholder_when_unset(self):
        # cog reads BOT_AUTHOR_LEGAL_NAME; the builder just takes the string
        embed = build_legal_embed(
            author="[set BOT_AUTHOR_LEGAL_NAME]",
            invite_url=None,
            support_url=None,
        )
        assert len(embed) <= _EMBED_LIMIT
        for field in embed.fields:
            assert len(field.value) <= _FIELD_LIMIT, field.name
