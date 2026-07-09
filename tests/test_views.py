import discord
from gurps_bot.ui.views import ConfirmView, PaginatorView


class TestPaginatorView:
    def test_initial_state(self):
        embeds = [discord.Embed(title=f"Page {i}") for i in range(3)]
        view = PaginatorView(embeds, author_id=123)
        assert view.current == 0
        assert view.prev_btn.disabled is True
        assert view.next_btn.disabled is False

    def test_single_page_both_disabled(self):
        embeds = [discord.Embed(title="Only page")]
        view = PaginatorView(embeds, author_id=123)
        assert view.prev_btn.disabled is True
        assert view.next_btn.disabled is True

    def test_update_buttons_mid_page(self):
        embeds = [discord.Embed(title=f"Page {i}") for i in range(3)]
        view = PaginatorView(embeds, author_id=123)
        view.current = 1
        view._update_buttons()
        assert view.prev_btn.disabled is False
        assert view.next_btn.disabled is False

    def test_update_buttons_last_page(self):
        embeds = [discord.Embed(title=f"Page {i}") for i in range(3)]
        view = PaginatorView(embeds, author_id=123)
        view.current = 2
        view._update_buttons()
        assert view.prev_btn.disabled is False
        assert view.next_btn.disabled is True

    def test_message_starts_none(self):
        embeds = [discord.Embed()]
        view = PaginatorView(embeds, author_id=123)
        assert view.message is None


class TestConfirmView:
    def test_initial_state(self):
        view = ConfirmView(author_id=456)
        assert view.confirmed is None
        assert view.message is None

    def test_timeout_default(self):
        view = ConfirmView(author_id=456)
        assert view.timeout == 30.0

    def test_custom_timeout(self):
        view = ConfirmView(author_id=456, timeout=60.0)
        assert view.timeout == 60.0
