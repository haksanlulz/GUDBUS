from gurps_bot.utils.sanitize import sanitize_name


class TestSanitizeName:
    def test_strips_markdown(self):
        assert sanitize_name("**Bold** _ital_") == "Bold ital"

    def test_strips_mention_chars(self):
        assert sanitize_name("@everyone <#channel>") == "everyone channel"

    def test_preserves_normal_chars(self):
        assert sanitize_name("Sir Brannar") == "Sir Brannar"

    def test_parens_survive(self):
        # Parens alone are inert markdown and appear in real catalog names
        # ("Vow (Chastity)"); stripping [ ] already breaks masked-link syntax
        # [text](url), so ( ) stay.
        assert sanitize_name("Vow (Chastity)") == "Vow (Chastity)"

    def test_masked_link_still_neutered(self):
        assert sanitize_name("[click me](https://x.example)") == "click me(https://x.example)"

    def test_empty_input(self):
        assert sanitize_name("") == ""

    def test_whitespace_only(self):
        assert sanitize_name("   ") == ""

    def test_unicode_preserved(self):
        assert sanitize_name("Ælfred") == "Ælfred"

    def test_strips_backticks(self):
        assert sanitize_name("`code`") == "code"

    def test_mixed_markdown_and_text(self):
        assert sanitize_name("~~Sir~~ *Brannar*") == "Sir Brannar"
