from locales.i18n import get_translations, get_translations_json, load_translations, t


def test_load_translations():
    translations = load_translations()
    assert "ug" in translations
    assert "en" in translations
    assert "navbar" in translations["ug"]
    assert "nav" in translations["ug"]
    assert "header" in translations["ug"]
    assert "navbar" in translations["en"]
    assert "nav" in translations["en"]
    assert "header" in translations["en"]


def test_t_function():
    # Uyghur translation
    assert t("header.brand_title", lang="ug") == "Kitabim OCR"
    assert t("tabs.sessions", lang="ug") == "يەرلىكتىكى خىزمەتلەر"
    assert (
        t("sessions.pages_completed_stat", lang="ug", done=5, total=10)
        == "5 / 10 بەت پۈتتى"
    )

    # English translation
    assert t("tabs.sessions", lang="en") == "Local Sessions"
    assert (
        t("sessions.pages_completed_stat", lang="en", done=5, total=10)
        == "5 / 10 pages done"
    )

    # Fallback to key or default
    assert t("nonexistent.key", lang="ug", default="Default Val") == "Default Val"
    assert t("nonexistent.key", lang="ug") == "nonexistent.key"


def test_get_translations():
    ug_dict = get_translations("ug")
    en_dict = get_translations("en")
    assert ug_dict["tabs"]["upload"] == "يېڭى PDF ھۆججەت"
    assert en_dict["tabs"]["upload"] == "Upload New PDF"


def test_get_translations_json():
    json_str = get_translations_json("ug")
    assert "يەرلىكتىكى خىزمەتلەر" in json_str
