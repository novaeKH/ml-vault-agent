from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_learning_dashboard_has_accessible_separate_view():
    html = (PROJECT_ROOT / "app" / "static" / "index.html").read_text(
        encoding="utf-8"
    )

    assert 'id="learning-button"' in html
    assert 'id="learning-view"' in html
    assert 'aria-label="Учебный маршрут"' in html
    assert 'id="skill-panel"' in html
    assert 'id="composer-wrap"' in html


def test_frontend_sends_only_explicit_selected_skill_to_chat():
    javascript = (PROJECT_ROOT / "app" / "static" / "app.js").read_text(
        encoding="utf-8"
    )

    assert "skill_id: appState.activeSkillId" in javascript
    assert "appState.activeSkillId = skill.id" in javascript
    assert "mode !== \"tutor\"" in javascript
    assert "Обычный чат сюда ничего не записывает" in javascript


def test_learning_layout_collapses_for_mobile():
    styles = (PROJECT_ROOT / "app" / "static" / "styles.css").read_text(
        encoding="utf-8"
    )

    mobile = styles[styles.index("@media (max-width: 820px)") :]
    assert ".learning-layout" in mobile
    assert "grid-template-columns: 1fr" in mobile
    assert ".skill-panel" in mobile
    assert "position: static" in mobile
